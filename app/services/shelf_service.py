"""My Shelf and Product Discovery domain services (Phase 9).

Implements:
- ShelfService: User-owned product shelf supporting both catalogue-linked and custom
  products, duplicate prevention, private notes isolation, reaction logging, and
  sensitivity cross-checks.
- DiscoveryService: Catalogue product discovery using Elasticsearch (with documented
  PostgreSQL fallback policy), canonical PostgreSQL hydration, and a transparent,
  versioned rule-based suitability engine ('tonetrace-discovery-rules-v1.0') with
  optional Gemini grounded explanations.
"""

import logging
import math
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, DependencyError, NotFoundError
from app.db.models import (
    Ingredient,
    IngredientEvidence,
    OCRJob,
    Product,
    ProductIngredient,
    ProductReaction,
    ProductVariant,
    SkinProfile,
    User,
    UserProduct,
    UserSensitivity,
)
from app.providers.gemini import LLMExplanationProvider
from app.providers.search_provider import SearchProvider, get_search_provider
from app.schemas.ai_explanations import ExplanationRequest, ExplanationResponse
from app.schemas.search import ProductSearchQuery
from app.schemas.shelf import (
    COMMERCIAL_SEGREGATION_NOTICE,
    CONCENTRATION_DISCLOSURE,
    PIGMENTATION_AND_MEDICAL_DISCLAIMER,
    RULE_ENGINE_VERSION,
    DiscoveryIngredientDetail,
    DiscoveryOfferSummary,
    DiscoveryProductDetailResponse,
    DiscoveryProductListResponse,
    DiscoveryProductSummaryItem,
    ProductReactionCreateInput,
    ProductReactionResponse,
    RecommendationAssessment,
    RuleEvaluationItem,
    ShelfItemCreateRequest,
    ShelfItemResponse,
    ShelfItemUpdateRequest,
    ShelfListResponse,
)
from app.services.explanation_service import ExplanationService
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

NEGATIVE_REACTION_TYPES = {
    "irritation",
    "redness",
    "breakout",
    "dryness",
    "stinging",
    "allergic_suspect",
}

GOAL_KEYWORD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "hyperpigmentation": (
        "hyperpigmentation",
        "pigmentation",
        "brightening",
        "dark spot",
        "uneven tone",
        "melanin",
        "niacinamide",
        "ascorbic",
        "azelaic",
        "tranexamic",
        "arbutin",
    ),
    "brightening": (
        "brightening",
        "hyperpigmentation",
        "radiance",
        "antioxidant",
        "vitamin c",
        "ascorbic",
        "niacinamide",
    ),
    "hydration": (
        "hydration",
        "humectant",
        "moistur",
        "hyaluronic",
        "glycerin",
        "panthenol",
        "water",
    ),
    "barrier_support": (
        "barrier",
        "ceramide",
        "panthenol",
        "cholesterol",
        "niacinamide",
        "soothing",
        "emollient",
    ),
    "redness": (
        "redness",
        "soothing",
        "calming",
        "azelaic",
        "centella",
        "panthenol",
        "allantoin",
        "barrier",
    ),
    "acne": (
        "acne",
        "blemish",
        "salicylic",
        "niacinamide",
        "azelaic",
        "sebum",
        "keratolytic",
    ),
    "texture": (
        "texture",
        "smoothing",
        "exfoli",
        "glycolic",
        "lactic",
        "salicylic",
        "retin",
    ),
}


def _tokenize_raw_ingredients(raw_text: str | None) -> list[str]:
    """Split raw packaging ingredient text into normalized tokens."""
    if not raw_text or not raw_text.strip():
        return []
    parts = re.split(r"[,;\n\r•\*]+", raw_text)
    cleaned: list[str] = []
    for part in parts:
        token = part.strip(" .:-•*()[]")
        if len(token) >= 2:
            cleaned.append(token)
    return cleaned


class ShelfService:
    """Domain service managing a user's personal product shelf and reaction history."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _get_user_sensitivity_set(self, user_id: UUID) -> set[str]:
        stmt = select(UserSensitivity.ingredient_name).where(UserSensitivity.user_id == user_id)
        res = await self._db.execute(stmt)
        return {name.strip().lower() for name in res.scalars().all() if name and name.strip()}

    async def add_shelf_item(
        self,
        user: User,
        payload: ShelfItemCreateRequest,
    ) -> ShelfItemResponse:
        """Add a catalogue-linked or custom product to the authenticated user's shelf."""
        product: Product | None = None
        is_custom = payload.product_id is None

        if payload.product_id is not None:
            prod_stmt = (
                select(Product)
                .where(Product.id == payload.product_id)
                .options(
                    selectinload(Product.product_ingredients).selectinload(
                        ProductIngredient.ingredient
                    )
                )
            )
            product = (await self._db.execute(prod_stmt)).scalar_one_or_none()
            if product is None:
                raise NotFoundError(f"Catalogue product '{payload.product_id}' was not found.")

            if payload.variant_id is not None:
                var_stmt = select(ProductVariant.id).where(
                    ProductVariant.id == payload.variant_id,
                    ProductVariant.product_id == product.id,
                )
                if (await self._db.execute(var_stmt)).scalar_one_or_none() is None:
                    raise NotFoundError(
                        f"Variant '{payload.variant_id}' not found for product '{product.id}'."
                    )

            # Prevent duplicate catalogue product on the user's shelf
            dup_stmt = select(UserProduct.id).where(
                UserProduct.user_id == user.id,
                UserProduct.product_id == product.id,
            )
            if (await self._db.execute(dup_stmt)).scalar_one_or_none() is not None:
                raise ConflictError(f"Product '{product.name}' is already on your shelf.")

            snapshot_name = payload.custom_name or product.name
            snapshot_brand = payload.custom_brand or product.brand
            snapshot_category = (payload.custom_category or product.category).lower()
            custom_ing_text = payload.custom_ingredient_text
        else:
            # Custom product
            snapshot_name = (payload.custom_name or "").strip()
            snapshot_brand = (payload.custom_brand or "").strip()
            snapshot_category = (payload.custom_category or "other").strip().lower()
            custom_ing_text = payload.custom_ingredient_text

            # Check duplicate custom product by (user_id, lower(custom_brand), lower(custom_name))
            dup_custom_stmt = select(UserProduct.id).where(
                UserProduct.user_id == user.id,
                UserProduct.is_custom.is_(True),
                func.lower(UserProduct.custom_brand) == snapshot_brand.lower(),
                func.lower(UserProduct.custom_name) == snapshot_name.lower(),
            )
            if (await self._db.execute(dup_custom_stmt)).scalar_one_or_none() is not None:
                raise ConflictError(
                    f"Custom product '{snapshot_brand} - {snapshot_name}' is already on your shelf."
                )

            if payload.ocr_job_id is not None:
                ocr_stmt = (
                    select(OCRJob)
                    .where(OCRJob.id == payload.ocr_job_id, OCRJob.user_id == user.id)
                    .options(selectinload(OCRJob.candidate_ingredients))
                )
                ocr_job = (await self._db.execute(ocr_stmt)).scalar_one_or_none()
                if ocr_job is None:
                    raise NotFoundError(
                        f"OCR scan '{payload.ocr_job_id}' not found for current user."
                    )
                if not custom_ing_text and ocr_job.candidate_ingredients:
                    custom_ing_text = ", ".join(
                        c.normalized_name for c in ocr_job.candidate_ingredients
                    )

        opened_at = payload.opened_at
        if opened_at and opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=UTC)

        expires_at = payload.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        shelf_item = UserProduct(
            user_id=user.id,
            product_id=payload.product_id,
            variant_id=payload.variant_id,
            ocr_job_id=payload.ocr_job_id,
            is_custom=is_custom,
            custom_name=snapshot_name,
            custom_brand=snapshot_brand,
            custom_category=snapshot_category,
            custom_ingredient_text=custom_ing_text,
            status=payload.status,
            opened_at=opened_at,
            expires_at=expires_at,
            purchase_price_minor_units=payload.purchase_price_minor_units,
            purchase_currency=payload.purchase_currency,
            private_notes=payload.private_notes,
            is_public=False,
        )
        self._db.add(shelf_item)
        await self._db.flush()

        if payload.initial_reaction is not None:
            await self._record_reaction(user.id, shelf_item, payload.initial_reaction)

        await self._db.commit()
        return await self.get_shelf_item(user.id, shelf_item.id)

    async def _record_reaction(
        self,
        user_id: UUID,
        shelf_item: UserProduct,
        reaction_input: ProductReactionCreateInput,
    ) -> ProductReaction:
        obs_at = reaction_input.observed_at or datetime.now(UTC)
        if obs_at.tzinfo is None:
            obs_at = obs_at.replace(tzinfo=UTC)

        reaction = ProductReaction(
            user_id=user_id,
            user_product_id=shelf_item.id,
            product_id=shelf_item.product_id,
            reaction_type=reaction_input.reaction_type,
            severity=reaction_input.severity,
            suspected_ingredient_names=[
                s.strip() for s in reaction_input.suspected_ingredient_names if s.strip()
            ],
            notes=reaction_input.notes,
            observed_at=obs_at,
        )
        self._db.add(reaction)
        await self._db.flush()
        return reaction

    async def get_shelf_item(self, user_id: UUID, item_id: UUID) -> ShelfItemResponse:
        """Retrieve a single shelf item strictly owned by user_id."""
        stmt = (
            select(UserProduct)
            .where(UserProduct.id == item_id, UserProduct.user_id == user_id)
            .options(
                selectinload(UserProduct.product)
                .selectinload(Product.product_ingredients)
                .selectinload(ProductIngredient.ingredient),
                selectinload(UserProduct.reactions),
            )
            .execution_options(populate_existing=True)
        )
        res = await self._db.execute(stmt)
        item = res.scalar_one_or_none()
        if item is None:
            raise NotFoundError(f"Shelf item '{item_id}' not found.")

        sensitivities = await self._get_user_sensitivity_set(user_id)
        return self._map_shelf_item(item, sensitivities)

    async def list_shelf_items(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        category_filter: str | None = None,
        is_custom_filter: bool | None = None,
        sort_by: str = "created_at_desc",
    ) -> ShelfListResponse:
        """List a user's shelf items with pagination, filters, and deterministic sorting."""
        filters = [UserProduct.user_id == user_id]
        if status_filter:
            filters.append(UserProduct.status == status_filter.strip().lower())
        if category_filter:
            filters.append(
                func.lower(UserProduct.custom_category) == category_filter.strip().lower()
            )
        if is_custom_filter is not None:
            filters.append(UserProduct.is_custom.is_(is_custom_filter))

        count_stmt = select(func.count(UserProduct.id)).where(*filters)
        total = int((await self._db.execute(count_stmt)).scalar_one() or 0)

        if sort_by == "name_asc":
            order_cols = [func.lower(UserProduct.custom_name).asc(), UserProduct.id.asc()]
        elif sort_by == "opened_at_desc":
            order_cols = [UserProduct.opened_at.desc().nulls_last(), UserProduct.created_at.desc()]
        else:
            order_cols = [UserProduct.created_at.desc(), UserProduct.id.asc()]

        offset = (page - 1) * page_size
        stmt = (
            select(UserProduct)
            .where(*filters)
            .options(
                selectinload(UserProduct.product)
                .selectinload(Product.product_ingredients)
                .selectinload(ProductIngredient.ingredient),
                selectinload(UserProduct.reactions),
            )
            .order_by(*order_cols)
            .limit(page_size)
            .offset(offset)
        )
        res = await self._db.execute(stmt)
        items = list(res.scalars().all())
        sensitivities = await self._get_user_sensitivity_set(user_id)

        total_pages = math.ceil(total / page_size) if page_size and total > 0 else 0
        return ShelfListResponse(
            items=[self._map_shelf_item(i, sensitivities) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def update_shelf_item(
        self,
        user_id: UUID,
        item_id: UUID,
        payload: ShelfItemUpdateRequest,
    ) -> ShelfItemResponse:
        """Update a user-owned shelf item and optionally record a new reaction observation."""
        stmt = (
            select(UserProduct)
            .where(UserProduct.id == item_id, UserProduct.user_id == user_id)
            .options(selectinload(UserProduct.reactions))
        )
        item = (await self._db.execute(stmt)).scalar_one_or_none()
        if item is None:
            raise NotFoundError(f"Shelf item '{item_id}' not found.")

        provided_fields = payload.model_fields_set
        if "status" in provided_fields and payload.status is not None:
            item.status = payload.status
        if "opened_at" in provided_fields:
            opened_at = payload.opened_at
            if opened_at and opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=UTC)
            item.opened_at = opened_at
        if "expires_at" in provided_fields:
            expires_at = payload.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            item.expires_at = expires_at
        if "purchase_price_minor_units" in provided_fields:
            item.purchase_price_minor_units = payload.purchase_price_minor_units
        if "purchase_currency" in provided_fields:
            item.purchase_currency = (
                payload.purchase_currency.strip().upper() if payload.purchase_currency else None
            )
        if "private_notes" in provided_fields:
            item.private_notes = payload.private_notes
        if "custom_name" in provided_fields and payload.custom_name:
            item.custom_name = payload.custom_name.strip()
        if "custom_brand" in provided_fields and payload.custom_brand:
            item.custom_brand = payload.custom_brand.strip()
        if "custom_category" in provided_fields and payload.custom_category:
            item.custom_category = payload.custom_category.strip().lower()
        if "custom_ingredient_text" in provided_fields:
            item.custom_ingredient_text = payload.custom_ingredient_text

        if payload.reaction is not None:
            await self._record_reaction(user_id, item, payload.reaction)
            if (
                payload.reaction.reaction_type in NEGATIVE_REACTION_TYPES
                and "status" not in provided_fields
            ):
                # Keep current status unless explicitly changed, or allow user full control
                pass

        await self._db.commit()
        return await self.get_shelf_item(user_id, item.id)

    async def delete_shelf_item(self, user_id: UUID, item_id: UUID) -> dict[str, str]:
        """Delete a shelf item strictly owned by user_id."""
        stmt = select(UserProduct).where(
            UserProduct.id == item_id,
            UserProduct.user_id == user_id,
        )
        item = (await self._db.execute(stmt)).scalar_one_or_none()
        if item is None:
            raise NotFoundError(f"Shelf item '{item_id}' not found.")

        await self._db.delete(item)
        await self._db.commit()
        return {"message": "Shelf item removed successfully.", "deleted_id": str(item_id)}

    def _map_shelf_item(
        self,
        item: UserProduct,
        user_sensitivities: set[str],
    ) -> ShelfItemResponse:
        product = item.product
        if item.is_custom:
            catalogue_status = "custom_entry"
            display_name = item.custom_name or "Custom Product"
            display_brand = item.custom_brand or "Custom Brand"
            display_category = item.custom_category or "other"
        elif product is not None:
            catalogue_status = "catalogue_linked"
            display_name = product.name
            display_brand = product.brand
            display_category = product.category
        else:
            # Product was linked originally, but catalogue record is now unavailable/deleted
            catalogue_status = "catalogue_unavailable"
            display_name = item.custom_name or "Unavailable Catalogue Product"
            display_brand = item.custom_brand or "Unknown Brand"
            display_category = item.custom_category or "unknown"

        ingredient_names: list[str] = []
        ingredient_data_status = "missing"
        if product is not None and product.product_ingredients:
            for pi in product.product_ingredients:
                if pi.ingredient:
                    ingredient_names.append(pi.ingredient.inci_name)
            ingredient_data_status = "complete" if ingredient_names else "missing"
        elif product is not None and product.full_ingredient_list:
            ingredient_names = _tokenize_raw_ingredients(product.full_ingredient_list)
            ingredient_data_status = "partial_text_only" if ingredient_names else "missing"
        elif item.custom_ingredient_text:
            ingredient_names = _tokenize_raw_ingredients(item.custom_ingredient_text)
            ingredient_data_status = "partial_text_only" if ingredient_names else "missing"

        sensitivity_alerts: list[str] = []
        if user_sensitivities and ingredient_names:
            for ing_name in ingredient_names:
                lower_ing = ing_name.lower()
                for sens in user_sensitivities:
                    if (
                        sens == lower_ing or sens in lower_ing
                    ) and ing_name not in sensitivity_alerts:
                        sensitivity_alerts.append(ing_name)

        incomplete_warning: str | None = None
        if ingredient_data_status != "complete":
            incomplete_warning = (
                "Ingredient data for this item is incomplete or unverified against canonical "
                "INCI records. Missing ingredient information is not proof of safety or "
                "absence of sensitizers."
            )

        return ShelfItemResponse(
            id=item.id,
            user_id=item.user_id,
            product_id=item.product_id,
            variant_id=item.variant_id,
            ocr_job_id=item.ocr_job_id,
            is_custom=item.is_custom,
            display_name=display_name,
            display_brand=display_brand,
            display_category=display_category,
            catalogue_status=catalogue_status,  # type: ignore[arg-type]
            ingredient_data_status=ingredient_data_status,  # type: ignore[arg-type]
            ingredient_names=ingredient_names,
            sensitivity_alerts=sensitivity_alerts,
            incomplete_ingredient_warning=incomplete_warning,
            status=item.status,
            opened_at=item.opened_at,
            expires_at=item.expires_at,
            purchase_price_minor_units=item.purchase_price_minor_units,
            purchase_currency=item.purchase_currency,
            private_notes=item.private_notes,
            is_public=item.is_public,
            reactions=[ProductReactionResponse.model_validate(r) for r in item.reactions],
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class DiscoveryService:
    """Product discovery service combining Elasticsearch, PostgreSQL, and explainable rules."""

    def __init__(
        self,
        db: AsyncSession,
        search_provider: SearchProvider | None = None,
        llm_provider: LLMExplanationProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._search_provider = search_provider or get_search_provider()
        self._llm_provider = llm_provider

    async def _load_user_context(
        self,
        user_id: UUID,
    ) -> tuple[SkinProfile | None, set[str], set[str], dict[UUID, UserProduct]]:
        """Load user skin profile, known sensitivities, reaction suspects, and shelf map."""
        sp_stmt = select(SkinProfile).where(SkinProfile.user_id == user_id)
        skin_profile = (await self._db.execute(sp_stmt)).scalar_one_or_none()

        sens_stmt = select(UserSensitivity.ingredient_name).where(
            UserSensitivity.user_id == user_id
        )
        sens_names = {
            s.strip().lower() for s in (await self._db.execute(sens_stmt)).scalars().all() if s
        }

        react_stmt = select(ProductReaction).where(
            ProductReaction.user_id == user_id,
            ProductReaction.reaction_type.in_(NEGATIVE_REACTION_TYPES),
        )
        reactions = list((await self._db.execute(react_stmt)).scalars().all())
        reaction_suspects: set[str] = set()
        for r in reactions:
            for ing in r.suspected_ingredient_names or []:
                if ing and ing.strip():
                    reaction_suspects.add(ing.strip().lower())

        shelf_stmt = select(UserProduct).where(
            UserProduct.user_id == user_id,
            UserProduct.product_id.is_not(None),
        )
        shelf_items = list((await self._db.execute(shelf_stmt)).scalars().all())
        shelf_map = {item.product_id: item for item in shelf_items if item.product_id is not None}

        return skin_profile, sens_names, reaction_suspects, shelf_map

    def _evaluate_product_rules(
        self,
        product: Product,
        skin_profile: SkinProfile | None,
        user_sensitivities: set[str],
        reaction_suspects: set[str],
        explicit_exclusions: set[str],
        target_goal: str | None = None,
    ) -> RecommendationAssessment:
        """Run the versioned, transparent rule-based suitability engine on a PostgreSQL Product."""
        rules: list[RuleEvaluationItem] = []
        prod_source_id = f"prod:{product.id}"
        base_score = 60

        # Extract canonical ingredients & raw tokens
        canonical_pis: list[ProductIngredient] = list(product.product_ingredients or [])
        raw_tokens = _tokenize_raw_ingredients(product.full_ingredient_list)

        if canonical_pis:
            ing_data_status = "complete"
            r1 = RuleEvaluationItem(
                rule_id="R1_INGREDIENT_DATA_COMPLETENESS",
                rule_version="1.0",
                outcome="pass",
                score_delta=0,
                explanation=(
                    f"Product has {len(canonical_pis)} canonical INCI ingredient record(s) "
                    "linked in PostgreSQL."
                ),
                source_ids=[prod_source_id],
            )
        elif raw_tokens:
            ing_data_status = "partial_text_only"
            base_score -= 15
            r1 = RuleEvaluationItem(
                rule_id="R1_INGREDIENT_DATA_COMPLETENESS",
                rule_version="1.0",
                outcome="warning",
                score_delta=-15,
                explanation=(
                    "Product has raw packaging ingredient text only without canonical INCI "
                    "records. Unverified or incomplete ingredient data is never treated as "
                    "proof of safety."
                ),
                source_ids=[prod_source_id],
            )
        else:
            ing_data_status = "missing"
            base_score -= 30
            r1 = RuleEvaluationItem(
                rule_id="R1_INGREDIENT_DATA_COMPLETENESS",
                rule_version="1.0",
                outcome="warning",
                score_delta=-30,
                explanation=(
                    "Ingredient list is missing in the catalogue. Missing ingredient "
                    "information is never treated as proof of safety or absence of sensitizers."
                ),
                source_ids=[prod_source_id],
            )
        rules.append(r1)

        # Rule 2: Sensitivity & Past Reaction Exclusion
        all_avoid_terms = user_sensitivities | explicit_exclusions
        matched_sensitivities: list[str] = []
        matched_reaction_suspects: list[str] = []
        r2_source_ids: list[str] = [prod_source_id]

        for pi in canonical_pis:
            ing: Ingredient | None = pi.ingredient
            if not ing:
                continue
            candidate_strings = [ing.inci_name.lower()]
            if ing.common_name:
                candidate_strings.append(ing.common_name.lower())
            for alias in ing.aliases or []:
                candidate_strings.append(str(alias).lower())

            for avoid in all_avoid_terms:
                if any(avoid == c or avoid in c for c in candidate_strings):
                    if ing.inci_name not in matched_sensitivities:
                        matched_sensitivities.append(ing.inci_name)
                    ing_sid = f"ing:{ing.id}"
                    if ing_sid not in r2_source_ids:
                        r2_source_ids.append(ing_sid)

            for suspect in reaction_suspects:
                if any(suspect == c or suspect in c for c in candidate_strings):
                    if ing.inci_name not in matched_reaction_suspects:
                        matched_reaction_suspects.append(ing.inci_name)
                    ing_sid = f"ing:{ing.id}"
                    if ing_sid not in r2_source_ids:
                        r2_source_ids.append(ing_sid)

        # Also check raw tokens if canonical_pis did not catch it
        for token in raw_tokens:
            t_low = token.lower()
            for avoid in all_avoid_terms:
                if (avoid == t_low or avoid in t_low) and token not in matched_sensitivities:
                    matched_sensitivities.append(token)
            for suspect in reaction_suspects:
                if (
                    suspect == t_low or suspect in t_low
                ) and token not in matched_reaction_suspects:
                    matched_reaction_suspects.append(token)

        if matched_sensitivities or matched_reaction_suspects:
            base_score -= 55
            flagged_names = matched_sensitivities + [
                s for s in matched_reaction_suspects if s not in matched_sensitivities
            ]
            r2 = RuleEvaluationItem(
                rule_id="R2_SENSITIVITY_AND_REACTION_EXCLUSION",
                rule_version="1.0",
                outcome="disqualified",
                score_delta=-55,
                explanation=(
                    f"Contains ingredient(s) matching user sensitivities or past negative "
                    f"reactions: {', '.join(flagged_names)}."
                ),
                source_ids=r2_source_ids,
            )
        elif ing_data_status != "complete" and (all_avoid_terms or reaction_suspects):
            base_score -= 10
            r2 = RuleEvaluationItem(
                rule_id="R2_SENSITIVITY_AND_REACTION_EXCLUSION",
                rule_version="1.0",
                outcome="warning",
                score_delta=-10,
                explanation=(
                    "User has recorded sensitivities, and this product's ingredient data is "
                    "incomplete; absence of sensitizers cannot be verified."
                ),
                source_ids=[prod_source_id],
            )
        else:
            base_score += 10
            r2 = RuleEvaluationItem(
                rule_id="R2_SENSITIVITY_AND_REACTION_EXCLUSION",
                rule_version="1.0",
                outcome="pass",
                score_delta=10,
                explanation=(
                    "No known user sensitivities or negative-reaction suspects were found "
                    "in the verified ingredient list."
                ),
                source_ids=r2_source_ids,
            )
        rules.append(r2)

        # Rule 3: Goal & Scientific Evidence Alignment (strictly excluding marketing_claim)
        active_goals: list[str] = []
        if target_goal and target_goal.strip():
            active_goals.append(target_goal.strip().lower())
        if skin_profile is not None:
            for g in skin_profile.skin_goals or []:
                if str(g).strip().lower() not in active_goals:
                    active_goals.append(str(g).strip().lower())
            for c in skin_profile.skin_concerns or []:
                if str(c).strip().lower() not in active_goals:
                    active_goals.append(str(c).strip().lower())

        expanded_keywords: set[str] = set()
        for g in active_goals:
            expanded_keywords.add(g)
            for syn in GOAL_KEYWORD_SYNONYMS.get(g, ()):
                expanded_keywords.add(syn)

        matched_goal_ingredients: list[str] = []
        r3_source_ids: list[str] = [prod_source_id]
        for pi in canonical_pis:
            ing = pi.ingredient
            if not ing:
                continue
            # Inspect non-rejected, non-marketing evidence records
            valid_evidence: list[IngredientEvidence] = [
                ev
                for ev in (ing.evidence_items or [])
                if ev.evidence_category
                in ("published_research", "identity_reference", "human_interpretation")
                and ev.review_status != "rejected"
            ]
            searchable_blob = " ".join(
                [
                    ing.inci_name.lower(),
                    (ing.common_name or "").lower(),
                    (ing.function or "").lower(),
                    (ing.description or "").lower(),
                    *[
                        f"{ev.topic_or_target.lower()} {ev.summary_statement.lower()}"
                        for ev in valid_evidence
                    ],
                ]
            )
            if expanded_keywords and any(kw in searchable_blob for kw in expanded_keywords):
                if ing.inci_name not in matched_goal_ingredients:
                    matched_goal_ingredients.append(ing.inci_name)
                ing_sid = f"ing:{ing.id}"
                if ing_sid not in r3_source_ids:
                    r3_source_ids.append(ing_sid)
                for ev in valid_evidence:
                    ev_sid = f"ev:{ev.id}"
                    if ev_sid not in r3_source_ids:
                        r3_source_ids.append(ev_sid)

        if matched_goal_ingredients and not (matched_sensitivities or matched_reaction_suspects):
            delta_r3 = 20
            base_score += delta_r3
            r3 = RuleEvaluationItem(
                rule_id="R3_GOAL_AND_EVIDENCE_ALIGNMENT",
                rule_version="1.0",
                outcome="pass",
                score_delta=delta_r3,
                explanation=(
                    f"Contains source-backed ingredient(s) ({', '.join(matched_goal_ingredients)}) "
                    f"relevant to stated goals/concerns ({', '.join(active_goals)}). "
                    "Exact concentrations remain unknown unless verified, and cosmetic "
                    "formulations never guarantee pigmentation or clinical outcomes."
                ),
                source_ids=r3_source_ids,
            )
        elif active_goals:
            r3 = RuleEvaluationItem(
                rule_id="R3_GOAL_AND_EVIDENCE_ALIGNMENT",
                rule_version="1.0",
                outcome="neutral",
                score_delta=0,
                explanation=(
                    f"No specific source-backed active ingredients matched stated goals "
                    f"({', '.join(active_goals)})."
                ),
                source_ids=[prod_source_id],
            )
        else:
            r3 = RuleEvaluationItem(
                rule_id="R3_GOAL_AND_EVIDENCE_ALIGNMENT",
                rule_version="1.0",
                outcome="info",
                score_delta=0,
                explanation="No specific user skincare goal filter was supplied for alignment.",
                source_ids=[prod_source_id],
            )
        rules.append(r3)

        # Rule 4: Skin Type & Category Context
        user_skin_type = (
            skin_profile.skin_type.strip().lower()
            if (skin_profile and skin_profile.skin_type)
            else None
        )
        r4 = RuleEvaluationItem(
            rule_id="R4_SKIN_TYPE_CATEGORY_FIT",
            rule_version="1.0",
            outcome="info",
            score_delta=0,
            explanation=(
                f"Evaluated product category '{product.category}' for "
                f"self-reported skin type '{user_skin_type or 'unspecified'}'."
            ),
            source_ids=[prod_source_id],
        )
        rules.append(r4)

        # Rule 5: Commercial Offer Segregation
        offer_count = len(product.offers or [])
        r5 = RuleEvaluationItem(
            rule_id="R5_COMMERCIAL_OFFER_SEGREGATION",
            rule_version="1.0",
            outcome="info",
            score_delta=0,
            explanation=(
                f"Segregated {offer_count} commercial merchant offer(s) from suitability "
                "scoring; paid or retail offers never influence recommendation ranking."
            ),
            source_ids=[prod_source_id],
        )
        rules.append(r5)

        final_score = max(0, min(100, base_score))
        if matched_sensitivities or matched_reaction_suspects:
            tier = "avoid_sensitivity_match"
            final_score = min(final_score, 25)
            rationale = (
                f"Flagged for avoidance because it contains ingredient(s) matching your "
                f"recorded sensitivities or negative reaction history "
                f"({', '.join(matched_sensitivities or matched_reaction_suspects)})."
            )
        elif ing_data_status != "complete":
            tier = "insufficient_ingredient_data"
            final_score = min(final_score, 45)
            rationale = (
                "Suitability cannot be confirmed because the product's ingredient list is "
                "incomplete or unverified in the catalogue. Missing ingredient data is never "
                "treated as proof of safety."
            )
        elif matched_goal_ingredients:
            tier = "recommended_fit"
            rationale = (
                f"Compatible with your recorded sensitivities and contains source-backed "
                f"ingredient(s) ({', '.join(matched_goal_ingredients)}) aligned with your goals. "
                "Ingredient concentrations are unknown unless verified, and results for "
                "pigmentation are never guaranteed."
            )
        else:
            tier = "compatible_neutral"
            rationale = (
                "No recorded sensitivity conflicts were found in the verified ingredient list, "
                "though no specific goal-targeted active ingredients were matched."
            )

        return RecommendationAssessment(
            rule_engine_version=RULE_ENGINE_VERSION,
            suitability_tier=tier,  # type: ignore[arg-type]
            suitability_score=final_score,
            ingredient_data_status=ing_data_status,  # type: ignore[arg-type]
            missing_data_is_not_safety_proof=True,
            concentration_disclosure=CONCENTRATION_DISCLOSURE,
            matched_sensitivities=matched_sensitivities,
            matched_reaction_suspects=matched_reaction_suspects,
            matched_goal_ingredients=matched_goal_ingredients,
            rules_triggered=rules,
            summary_rationale=rationale,
            scientific_vs_commercial_notice=COMMERCIAL_SEGREGATION_NOTICE,
            pigmentation_and_medical_disclaimer=PIGMENTATION_AND_MEDICAL_DISCLAIMER,
        )

    async def discover_products(
        self,
        user: User,
        q: str | None = None,
        category: str | None = None,
        brand: str | None = None,
        goal: str | None = None,
        exclude_user_sensitivities: bool = True,
        exclude_ingredients: list[str] | None = None,
        require_complete_ingredients: bool = False,
        sort_by: str = "suitability_desc",
        page: int = 1,
        page_size: int = 20,
    ) -> DiscoveryProductListResponse:
        """Discover products using Elasticsearch (with documented fallback) and PostgreSQL."""
        skin_profile, user_sens, reaction_suspects, shelf_map = await self._load_user_context(
            user.id
        )
        explicit_exclusions = {
            i.strip().lower() for i in (exclude_ingredients or []) if i and i.strip()
        }
        effective_exclusions = (
            (user_sens | explicit_exclusions) if exclude_user_sensitivities else explicit_exclusions
        )

        search_backend_used = "postgresql_catalogue"
        degraded_warning: str | None = None
        es_ordered_ids: list[UUID] | None = None

        has_text_query = bool(q and q.strip())
        if has_text_query or self._settings.ELASTICSEARCH_ENABLED:
            if self._settings.ELASTICSEARCH_ENABLED:
                search_service = SearchService(
                    db=self._db,
                    search_provider=self._search_provider,
                    settings=self._settings,
                )
                es_sort = (
                    "name_asc"
                    if sort_by == "name_asc"
                    else "name_desc"
                    if sort_by == "name_desc"
                    else "updated_at_desc"
                    if sort_by == "updated_at_desc"
                    else "relevance"
                )
                es_query = ProductSearchQuery(
                    q=q.strip() if q and q.strip() else None,
                    brand=brand.strip() if brand and brand.strip() else None,
                    category=category.strip().lower() if category and category.strip() else None,
                    exclude_ingredients=sorted(effective_exclusions),
                    sort_by=es_sort,  # type: ignore[arg-type]
                    page=1,
                    page_size=100,
                )
                try:
                    es_results = await search_service.search_products(es_query)
                    es_ordered_ids = [hit.id for hit in es_results.items]
                    search_backend_used = "elasticsearch"
                except DependencyError:
                    if self._settings.ELASTICSEARCH_FALLBACK_TO_DB:
                        logger.warning(
                            "Elasticsearch unavailable during discovery; using PostgreSQL fallback."
                        )
                        search_backend_used = "postgresql_fallback"
                        degraded_warning = (
                            "Elasticsearch is currently unavailable; product discovery "
                            "results were served via the PostgreSQL catalogue fallback."
                        )
                    else:
                        raise
            elif has_text_query:
                if self._settings.ELASTICSEARCH_FALLBACK_TO_DB:
                    search_backend_used = "postgresql_fallback"
                    degraded_warning = (
                        "Elasticsearch is disabled; free-text discovery query was served "
                        "via the PostgreSQL catalogue fallback."
                    )
                else:
                    raise DependencyError(
                        "Search service is disabled by server configuration.",
                        status_code=503,
                    )

        # Hydrate canonical products from PostgreSQL
        stmt = select(Product).options(
            selectinload(Product.product_ingredients)
            .selectinload(ProductIngredient.ingredient)
            .selectinload(Ingredient.evidence_items),
            selectinload(Product.offers),
        )
        if es_ordered_ids is not None:
            if not es_ordered_ids:
                return DiscoveryProductListResponse(
                    items=[],
                    total=0,
                    page=page,
                    page_size=page_size,
                    total_pages=0,
                    search_backend_used=search_backend_used,  # type: ignore[arg-type]
                    degraded_search_warning=degraded_warning,
                )
            stmt = stmt.where(Product.id.in_(es_ordered_ids))
        else:
            if q and q.strip():
                pattern = f"%{q.strip()}%"
                stmt = stmt.where(
                    or_(
                        Product.name.ilike(pattern),
                        Product.brand.ilike(pattern),
                        Product.description.ilike(pattern),
                        Product.full_ingredient_list.ilike(pattern),
                    )
                )
            if category and category.strip():
                stmt = stmt.where(func.lower(Product.category) == category.strip().lower())
            if brand and brand.strip():
                stmt = stmt.where(func.lower(Product.brand) == brand.strip().lower())

        pg_products = list((await self._db.execute(stmt)).scalars().all())
        if es_ordered_ids is not None:
            order_index = {pid: idx for idx, pid in enumerate(es_ordered_ids)}
            pg_products.sort(key=lambda p: order_index.get(p.id, 999999))

        summary_items: list[DiscoveryProductSummaryItem] = []
        for product in pg_products:
            assessment = self._evaluate_product_rules(
                product=product,
                skin_profile=skin_profile,
                user_sensitivities=user_sens if exclude_user_sensitivities else set(),
                reaction_suspects=reaction_suspects if exclude_user_sensitivities else set(),
                explicit_exclusions=explicit_exclusions,
                target_goal=goal,
            )

            # Filter out products with matched exclusions when requested
            if (exclude_user_sensitivities or explicit_exclusions) and (
                assessment.matched_sensitivities or assessment.matched_reaction_suspects
            ):
                continue

            if require_complete_ingredients and assessment.ingredient_data_status != "complete":
                continue

            in_stock_offers = [o for o in (product.offers or []) if o.is_in_stock]
            candidate_offers = in_stock_offers or list(product.offers or [])
            lowest_offer = (
                min(candidate_offers, key=lambda o: o.price_minor_units)
                if candidate_offers
                else None
            )

            shelf_entry = shelf_map.get(product.id)
            summary_items.append(
                DiscoveryProductSummaryItem(
                    product_id=product.id,
                    source_id=f"prod:{product.id}",
                    name=product.name,
                    brand=product.brand,
                    category=product.category,
                    description=product.description,
                    image_url=product.image_url,
                    ingredient_count=len(product.product_ingredients or []),
                    ingredient_data_status=assessment.ingredient_data_status,
                    on_user_shelf=shelf_entry is not None,
                    user_shelf_status=shelf_entry.status if shelf_entry else None,
                    lowest_offer_minor_units=(
                        lowest_offer.price_minor_units if lowest_offer else None
                    ),
                    lowest_offer_currency=lowest_offer.currency if lowest_offer else None,
                    recommendation=assessment,
                )
            )

        # Deterministic sorting
        if sort_by == "name_asc":
            summary_items.sort(key=lambda item: (item.name.lower(), str(item.product_id)))
        elif sort_by == "name_desc":
            summary_items.sort(
                key=lambda item: (item.name.lower(), str(item.product_id)),
                reverse=True,
            )
        elif sort_by == "suitability_desc":
            summary_items.sort(
                key=lambda item: (-item.recommendation.suitability_score, item.name.lower())
            )
        # If sort_by == 'relevance' and es_ordered_ids was used, preserve ES score order

        total = len(summary_items)
        offset = (page - 1) * page_size
        paged_items = summary_items[offset : offset + page_size]
        total_pages = math.ceil(total / page_size) if page_size and total > 0 else 0

        return DiscoveryProductListResponse(
            items=paged_items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            search_backend_used=search_backend_used,  # type: ignore[arg-type]
            degraded_search_warning=degraded_warning,
        )

    async def get_discovery_product_detail(
        self,
        user: User,
        product_id: UUID,
        goal: str | None = None,
        include_ai_explanation: bool = False,
    ) -> DiscoveryProductDetailResponse:
        """Retrieve canonical PostgreSQL product detail, rules, and optional AI explanation."""
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.ingredient_lists),
                selectinload(Product.product_ingredients)
                .selectinload(ProductIngredient.ingredient)
                .selectinload(Ingredient.evidence_items),
                selectinload(Product.offers),
            )
        )
        product = (await self._db.execute(stmt)).scalar_one_or_none()
        if product is None:
            raise NotFoundError(f"Catalogue product '{product_id}' not found.")

        skin_profile, user_sens, reaction_suspects, shelf_map = await self._load_user_context(
            user.id
        )
        assessment = self._evaluate_product_rules(
            product=product,
            skin_profile=skin_profile,
            user_sensitivities=user_sens,
            reaction_suspects=reaction_suspects,
            explicit_exclusions=set(),
            target_goal=goal,
        )

        current_formula_version: str | None = None
        for il in product.ingredient_lists or []:
            if il.is_current:
                current_formula_version = il.formula_version
                break

        ingredient_details: list[DiscoveryIngredientDetail] = []
        ingredient_ids_for_ai: list[UUID] = []
        for pi in product.product_ingredients or []:
            ing = pi.ingredient
            if not ing:
                continue
            ingredient_ids_for_ai.append(ing.id)
            valid_ev = [
                ev
                for ev in (ing.evidence_items or [])
                if ev.evidence_category
                in ("published_research", "identity_reference", "human_interpretation")
                and ev.review_status != "rejected"
            ]
            is_sens = any(
                s == ing.inci_name.lower()
                or s in ing.inci_name.lower()
                or (ing.common_name and s in ing.common_name.lower())
                for s in (user_sens | reaction_suspects)
            )
            ingredient_details.append(
                DiscoveryIngredientDetail(
                    ingredient_id=ing.id,
                    source_id=f"ing:{ing.id}",
                    inci_name=ing.inci_name,
                    common_name=ing.common_name,
                    position=pi.position,
                    function=ing.function,
                    concentration_percentage=pi.concentration_percentage,
                    concentration_status=(
                        "verified_percentage"
                        if pi.concentration_percentage is not None
                        else "unknown_order_only"
                    ),
                    is_user_sensitivity_match=is_sens,
                    evidence_count=len(valid_ev),
                    evidence_summaries=[ev.summary_statement for ev in valid_ev[:3]],
                    evidence_source_ids=[f"ev:{ev.id}" for ev in valid_ev],
                )
            )

        offers_list = [
            DiscoveryOfferSummary(
                offer_id=o.id,
                merchant_name=o.merchant_name,
                price_minor_units=o.price_minor_units,
                currency=o.currency,
                is_in_stock=o.is_in_stock,
                offer_url=o.offer_url,
                retrieved_at=o.retrieved_at,
            )
            for o in (product.offers or [])
        ]

        ai_explanation: ExplanationResponse | None = None
        if include_ai_explanation:
            explanation_service = ExplanationService(
                db=self._db,
                llm_provider=self._llm_provider,
                settings=self._settings,
            )
            goal_phrase = f" for goal '{goal}'" if goal else ""
            ai_req = ExplanationRequest(
                schema_version="1.0",
                question=(
                    f"Explain the suitability and ingredient evidence of {product.brand} "
                    f"{product.name}{goal_phrase} based strictly on retrieved catalogue and "
                    "evidence records."
                ),
                product_ids=[product.id],
                ingredient_ids=ingredient_ids_for_ai[:10],
                include_user_skin_profile=True,
            )
            ai_explanation = await explanation_service.generate_explanation(
                request=ai_req,
                user=user,
            )

        shelf_entry = shelf_map.get(product.id)
        return DiscoveryProductDetailResponse(
            product_id=product.id,
            source_id=f"prod:{product.id}",
            name=product.name,
            brand=product.brand,
            category=product.category,
            description=product.description,
            ean_or_upc=product.ean_or_upc,
            image_url=product.image_url,
            formula_version=current_formula_version,
            full_ingredient_list=product.full_ingredient_list,
            ingredient_data_status=assessment.ingredient_data_status,
            ingredients=ingredient_details,
            commercial_offers=offers_list,
            on_user_shelf=shelf_entry is not None,
            user_shelf_item_id=shelf_entry.id if shelf_entry else None,
            user_shelf_status=shelf_entry.status if shelf_entry else None,
            recommendation=assessment,
            grounded_ai_explanation=ai_explanation,
        )
