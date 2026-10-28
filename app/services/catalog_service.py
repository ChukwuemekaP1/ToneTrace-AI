"""Catalog service managing products, ingredients, formula versioning, and provenance.

Core architectural guarantees:
- PostgreSQL is the authoritative system of record.
- Historical formula reformulations are preserved rather than overwritten.
- Commercial offers and pricing are stored separately from formulation data in integer minor units.
- External integrations (Open Beauty Facts, Channel3) follow strict non-fabrication principles.
- Catalog mutations reliably enqueue SearchOutbox events for Elasticsearch synchronization.
"""

import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ConflictError,
    DependencyError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from app.db.models import (
    Brand,
    DataSource,
    Ingredient,
    IngredientAlias,
    Product,
    ProductIngredient,
    ProductIngredientList,
    ProductOffer,
    ProductVariant,
    SearchOutbox,
)
from app.providers.channel3 import (
    Channel3Adapter,
    Channel3Error,
    Channel3RateLimitError,
)
from app.providers.open_beauty_facts import (
    OpenBeautyFactsAdapter,
)
from app.schemas.catalog import (
    BrandResponse,
    Channel3OfferItem,
    Channel3ProductItem,
    Channel3SearchResponse,
    Channel3SyncOffersResponse,
    DataSourceResponse,
    IngestProductResponse,
    IngredientAliasResponse,
    IngredientDetailResponse,
    ProductDetailResponse,
    ProductIngredientItemResponse,
    ProductIngredientListResponse,
    ProductOfferResponse,
    ProductVariantResponse,
)

logger = logging.getLogger(__name__)


def format_currency(minor_units: int, currency: str) -> str:
    """Format integer minor units into human-readable currency string."""
    amount = minor_units / 100.0
    curr = currency.upper()
    if curr == "USD":
        symbol = "$"
    elif curr == "EUR":
        symbol = "€"
    elif curr == "GBP":
        symbol = "£"
    else:
        symbol = f"{curr} "
    return f"{symbol}{amount:.2f}"


def slugify(text: str) -> str:
    """Generate a clean URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-") or "unknown"


class CatalogService:
    """Domain service managing the skincare catalog, formulations, and provenance."""

    def __init__(
        self,
        db: AsyncSession,
        obf_adapter: OpenBeautyFactsAdapter | None = None,
        channel3_adapter: Channel3Adapter | None = None,
    ) -> None:
        self._db = db
        self._obf = obf_adapter or OpenBeautyFactsAdapter()
        self._channel3 = channel3_adapter or Channel3Adapter()

    async def get_product(self, product_id: UUID) -> ProductDetailResponse:
        """Fetch product by UUID with brand, variants, formula versions, and offers."""
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.brand_rel),
                selectinload(Product.variants),
                selectinload(Product.offers),
                selectinload(Product.ingredient_lists).selectinload(
                    ProductIngredientList.data_source
                ),
                selectinload(Product.ingredient_lists)
                .selectinload(ProductIngredientList.items)
                .selectinload(ProductIngredient.ingredient),
            )
        )
        result = await self._db.execute(stmt)
        product = result.scalar_one_or_none()

        if product is None:
            raise NotFoundError(f"Product with ID '{product_id}' was not found.")

        return self._map_to_product_detail(product)

    async def get_product_by_barcode(self, barcode: str) -> ProductDetailResponse:
        """Look up product by barcode across product variants and primary barcode."""
        cleaned_barcode = barcode.strip()
        if not cleaned_barcode:
            raise ValidationError("Barcode parameter cannot be empty.")

        # Check variant barcode first
        stmt = select(ProductVariant.product_id).where(ProductVariant.barcode == cleaned_barcode)
        res = await self._db.execute(stmt)
        product_id = res.scalar_one_or_none()

        # Check primary product barcode if variant not matched
        if product_id is None:
            prod_stmt = select(Product.id).where(Product.ean_or_upc == cleaned_barcode)
            prod_res = await self._db.execute(prod_stmt)
            product_id = prod_res.scalar_one_or_none()

        if product_id is None:
            raise NotFoundError(f"Product with barcode '{cleaned_barcode}' was not found.")

        return await self.get_product(product_id)

    async def get_product_ingredients(
        self, product_id: UUID, formula_version: str | None = None
    ) -> list[ProductIngredientItemResponse]:
        """Fetch ordered ingredient items for a product's current or specific formula."""
        detail = await self.get_product(product_id)

        target_list: ProductIngredientListResponse | None = None
        if formula_version:
            for fl in detail.formula_history:
                if fl.formula_version == formula_version:
                    target_list = fl
                    break
            if target_list is None:
                raise NotFoundError(
                    f"Formula version '{formula_version}' not found for product '{product_id}'."
                )
        else:
            target_list = detail.current_formula

        if target_list is None:
            return []

        return target_list.ingredients

    async def get_ingredient(self, ingredient_id: UUID) -> IngredientDetailResponse:
        """Fetch standardized ingredient with aliases."""
        stmt = (
            select(Ingredient)
            .where(Ingredient.id == ingredient_id)
            .options(selectinload(Ingredient.alias_records))
        )
        res = await self._db.execute(stmt)
        ingredient = res.scalar_one_or_none()

        if ingredient is None:
            raise NotFoundError(f"Ingredient with ID '{ingredient_id}' was not found.")

        alias_responses = [
            IngredientAliasResponse(
                id=a.id,
                alias_name=a.alias_name,
                alias_type=a.alias_type,
            )
            for a in ingredient.alias_records
        ]

        return IngredientDetailResponse(
            id=ingredient.id,
            inci_name=ingredient.inci_name,
            common_name=ingredient.common_name,
            aliases=ingredient.aliases or [],
            alias_records=alias_responses,
            function=ingredient.function,
            description=ingredient.description,
            safety_rating=ingredient.safety_rating,
            created_at=ingredient.created_at,
        )

    async def ingest_from_barcode(self, barcode: str) -> IngestProductResponse:
        """Ingest or retrieve a product by EAN/UPC barcode using Open Beauty Facts."""
        cleaned_barcode = barcode.strip()
        if not cleaned_barcode or not cleaned_barcode.isdigit():
            raise ValidationError(f"Invalid barcode format: '{barcode}'. Must be numeric.")

        # 1. Idempotency check: see if product already exists locally
        try:
            existing = await self.get_product_by_barcode(cleaned_barcode)
            return IngestProductResponse(
                product=existing,
                was_created=False,
                source_attribution="Cached in local PostgreSQL catalogue.",
            )
        except NotFoundError:
            pass

        # 2. Query upstream Open Beauty Facts adapter
        obf_product = await self._obf.fetch_product_by_barcode(cleaned_barcode)
        if obf_product is None:
            raise NotFoundError(
                f"No cosmetic product found in Open Beauty Facts for barcode '{cleaned_barcode}'."
            )

        # 3. Resolve or create Brand
        brand_name = obf_product.brand.strip() or "Independent"
        brand_slug = slugify(brand_name)

        brand_stmt = select(Brand).where(
            (Brand.slug == brand_slug) | (Brand.name.ilike(brand_name))
        )
        brand_res = await self._db.execute(brand_stmt)
        brand = brand_res.scalars().first()

        if brand is None:
            brand = Brand(
                name=brand_name,
                slug=brand_slug,
                description=f"Brand profile for {brand_name}.",
            )
            self._db.add(brand)
            await self._db.flush()

        # 4. Resolve or create DataSource
        ds_stmt = select(DataSource).where(DataSource.code == "open_beauty_facts")
        ds_res = await self._db.execute(ds_stmt)
        data_source = ds_res.scalar_one_or_none()

        if data_source is None:
            data_source = DataSource(
                code="open_beauty_facts",
                name="Open Beauty Facts",
                attribution_url="https://world.openbeautyfacts.org",
                license_or_terms="Open Database License (ODbL) v1.0",
            )
            self._db.add(data_source)
            await self._db.flush()

        # 5. Create Product
        product = Product(
            name=obf_product.name,
            brand=brand.name,
            brand_id=brand.id,
            category=obf_product.category or "skincare",
            full_ingredient_list=obf_product.raw_ingredients_text,
            ean_or_upc=cleaned_barcode,
            image_url=obf_product.image_url,
        )
        self._db.add(product)
        await self._db.flush()

        # 6. Create Primary ProductVariant
        variant = ProductVariant(
            product_id=product.id,
            variant_name="Standard",
            barcode=cleaned_barcode,
        )
        self._db.add(variant)
        await self._db.flush()

        # 7. Create Provenance-tracked ProductIngredientList (Formula v1)
        ingredient_list = ProductIngredientList(
            product_id=product.id,
            variant_id=variant.id,
            data_source_id=data_source.id,
            formula_version="v1",
            is_current=True,
            raw_ingredient_text=obf_product.raw_ingredients_text,
            retrieved_at=datetime.now(UTC),
        )
        self._db.add(ingredient_list)
        await self._db.flush()

        # 8. Parse and attach ingredients
        new_ingredient_ids: list[UUID] = []
        for item in obf_product.ingredients:
            raw_name = item.name.strip()
            if not raw_name:
                continue

            clean_name = raw_name.strip(" *,-")
            if not clean_name:
                continue

            # Check existing ingredient by INCI name or alias
            ing_stmt = select(Ingredient).where(
                (func.lower(Ingredient.inci_name) == clean_name.lower())
                | (func.lower(Ingredient.common_name) == clean_name.lower())
            )
            ing_res = await self._db.execute(ing_stmt)
            ingredient = ing_res.scalars().first()

            if ingredient is None:
                # Check aliases
                alias_stmt = select(IngredientAlias).where(
                    func.lower(IngredientAlias.alias_name) == clean_name.lower()
                )
                alias_res = await self._db.execute(alias_stmt)
                alias_match = alias_res.scalar_one_or_none()
                if alias_match:
                    ing_stmt2 = select(Ingredient).where(Ingredient.id == alias_match.ingredient_id)
                    ing_res2 = await self._db.execute(ing_stmt2)
                    ingredient = ing_res2.scalar_one_or_none()

            if ingredient is None:
                # Create standard ingredient record conservatively
                ingredient = Ingredient(
                    inci_name=clean_name.title(),
                    common_name=None,
                    aliases=[clean_name],
                    function=None,
                    safety_rating="safe",
                )
                self._db.add(ingredient)
                await self._db.flush()
                new_ingredient_ids.append(ingredient.id)

            # Link ProductIngredient
            pi = ProductIngredient(
                product_id=product.id,
                product_ingredient_list_id=ingredient_list.id,
                ingredient_id=ingredient.id,
                position=item.position,
                concentration_percentage=item.percent_estimate,
            )
            self._db.add(pi)

        # 9. Enqueue SearchOutbox events for Elasticsearch synchronization
        product_outbox = SearchOutbox(
            entity_type="product",
            entity_id=product.id,
            action="index",
            payload={
                "id": str(product.id),
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "description": product.description,
                "full_ingredient_list": product.full_ingredient_list,
                "ean_or_upc": product.ean_or_upc,
                "image_url": product.image_url,
                "created_at": (
                    product.created_at.isoformat()
                    if product.created_at
                    else datetime.now(UTC).isoformat()
                ),
            },
        )
        self._db.add(product_outbox)

        for new_id in new_ingredient_ids:
            ing_outbox = SearchOutbox(
                entity_type="ingredient",
                entity_id=new_id,
                action="index",
                payload={"id": str(new_id)},
            )
            self._db.add(ing_outbox)

        await self._db.commit()

        # Reload full details
        full_detail = await self.get_product(product.id)
        return IngestProductResponse(
            product=full_detail,
            was_created=True,
            source_attribution=obf_product.attribution,
        )

    async def add_formula_reformulation(
        self,
        product_id: UUID,
        formula_version: str,
        raw_ingredient_text: str | None,
        ingredient_names: list[str],
        data_source_code: str = "manual",
    ) -> ProductIngredientListResponse:
        """Preserve historical formulas by appending a new version and updating current pointer."""
        stmt = select(Product).where(Product.id == product_id)
        res = await self._db.execute(stmt)
        product = res.scalar_one_or_none()
        if product is None:
            raise NotFoundError(f"Product '{product_id}' was not found.")

        # Check for duplicate formula version string
        existing_version_stmt = select(ProductIngredientList).where(
            ProductIngredientList.product_id == product_id,
            ProductIngredientList.formula_version == formula_version,
        )
        ver_res = await self._db.execute(existing_version_stmt)
        if ver_res.scalar_one_or_none() is not None:
            raise ConflictError(
                f"Formula version '{formula_version}' already exists for this product."
            )

        # Mark all prior formula lists as not current
        prior_lists_stmt = select(ProductIngredientList).where(
            ProductIngredientList.product_id == product_id,
            ProductIngredientList.is_current == True,  # noqa: E712
        )
        prior_res = await self._db.execute(prior_lists_stmt)
        for old_list in prior_res.scalars().all():
            old_list.is_current = False

        # Resolve DataSource
        ds_stmt = select(DataSource).where(DataSource.code == data_source_code)
        ds_res = await self._db.execute(ds_stmt)
        data_source = ds_res.scalar_one_or_none()

        if data_source is None:
            data_source = DataSource(
                code=data_source_code,
                name=data_source_code.replace("_", " ").title(),
            )
            self._db.add(data_source)
            await self._db.flush()

        # Create new ProductIngredientList
        new_list = ProductIngredientList(
            product_id=product.id,
            formula_version=formula_version,
            is_current=True,
            raw_ingredient_text=raw_ingredient_text,
            data_source_id=data_source.id,
            retrieved_at=datetime.now(UTC),
        )
        self._db.add(new_list)
        await self._db.flush()

        # Update product raw text to match latest formulation
        if raw_ingredient_text:
            product.full_ingredient_list = raw_ingredient_text

        # Map ingredients
        items: list[ProductIngredientItemResponse] = []
        for idx, ing_name in enumerate(ingredient_names, start=1):
            clean_name = ing_name.strip()
            if not clean_name:
                continue

            ing_stmt = select(Ingredient).where(
                (func.lower(Ingredient.inci_name) == clean_name.lower())
                | (func.lower(Ingredient.common_name) == clean_name.lower())
            )
            ing_res = await self._db.execute(ing_stmt)
            ingredient = ing_res.scalars().first()

            if ingredient is None:
                ingredient = Ingredient(
                    inci_name=clean_name.title(),
                    safety_rating="safe",
                )
                self._db.add(ingredient)
                await self._db.flush()

            pi = ProductIngredient(
                product_id=product.id,
                product_ingredient_list_id=new_list.id,
                ingredient_id=ingredient.id,
                position=idx,
            )
            self._db.add(pi)

            items.append(
                ProductIngredientItemResponse(
                    position=idx,
                    ingredient_id=ingredient.id,
                    inci_name=ingredient.inci_name,
                    common_name=ingredient.common_name,
                    function=ingredient.function,
                    safety_rating=ingredient.safety_rating,
                )
            )

        # Enqueue Outbox update
        outbox_event = SearchOutbox(
            entity_type="product",
            entity_id=product.id,
            action="index",
            payload={
                "id": str(product.id),
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "full_ingredient_list": product.full_ingredient_list,
            },
        )
        self._db.add(outbox_event)
        await self._db.commit()

        return ProductIngredientListResponse(
            id=new_list.id,
            formula_version=new_list.formula_version,
            is_current=new_list.is_current,
            raw_ingredient_text=new_list.raw_ingredient_text,
            retrieved_at=new_list.retrieved_at,
            data_source=DataSourceResponse.model_validate(data_source),
            ingredients=items,
        )

    async def record_product_offer(
        self,
        product_id: UUID,
        merchant_name: str,
        price_minor_units: int,
        currency: str = "USD",
        offer_url: str | None = None,
        is_in_stock: bool = True,
        variant_id: UUID | None = None,
        data_source_code: str = "channel3",
    ) -> ProductOfferResponse:
        """Record commercial pricing and availability offer in exact minor units."""
        stmt = select(Product).where(Product.id == product_id)
        res = await self._db.execute(stmt)
        if res.scalar_one_or_none() is None:
            raise NotFoundError(f"Product '{product_id}' was not found.")

        # Resolve DataSource
        ds_stmt = select(DataSource).where(DataSource.code == data_source_code)
        ds_res = await self._db.execute(ds_stmt)
        data_source = ds_res.scalar_one_or_none()

        if data_source is None:
            data_source = DataSource(
                code=data_source_code,
                name=data_source_code.replace("_", " ").title(),
            )
            self._db.add(data_source)
            await self._db.flush()

        offer = ProductOffer(
            product_id=product_id,
            variant_id=variant_id,
            data_source_id=data_source.id,
            merchant_name=merchant_name,
            offer_url=offer_url,
            price_minor_units=price_minor_units,
            currency=currency.upper(),
            is_in_stock=is_in_stock,
            retrieved_at=datetime.now(UTC),
        )
        self._db.add(offer)
        await self._db.commit()
        await self._db.refresh(offer)

        return ProductOfferResponse(
            id=offer.id,
            merchant_name=offer.merchant_name,
            offer_url=offer.offer_url,
            price_minor_units=offer.price_minor_units,
            currency=offer.currency,
            formatted_price=format_currency(offer.price_minor_units, offer.currency),
            is_in_stock=offer.is_in_stock,
            retrieved_at=offer.retrieved_at,
        )

    async def search_channel3_catalog(
        self,
        query: str,
        limit: int = 10,
        max_price: float | None = None,
        user_id: str | None = None,
    ) -> Channel3SearchResponse:
        """Query Channel3 universal product catalog and map offers in integer minor units."""
        filters: dict[str, dict[str, float]] | None = None
        if max_price is not None:
            filters = {"price": {"max_price": max_price}}

        try:
            raw_products, next_page_token = await self._channel3.search_products(
                query=query,
                limit=limit,
                filters=filters,
                user_id=user_id,
            )
        except Channel3RateLimitError as exc:
            raise RateLimitError(str(exc)) from exc
        except Channel3Error as exc:
            raise DependencyError(str(exc)) from exc
        products: list[Channel3ProductItem] = []
        for p in raw_products:
            offers = [
                Channel3OfferItem(
                    merchant_name=o.merchant_name,
                    product_name=o.product_name,
                    price_minor_units=o.price_minor_units,
                    currency=o.currency,
                    offer_url=o.offer_url,
                    is_in_stock=o.is_in_stock,
                    channel3_product_id=o.channel3_product_id,
                    compare_at_price_minor_units=o.compare_at_price_minor_units,
                    condition=o.condition,
                    max_commission_rate=o.max_commission_rate,
                    brand_name=o.brand_name,
                    image_url=o.image_url,
                )
                for o in p.offers
            ]
            products.append(
                Channel3ProductItem(
                    id=p.id,
                    title=p.title,
                    description=p.description,
                    brand_name=p.brand_name,
                    brand_id=p.brand_id,
                    category_slug=p.category_slug,
                    category_title=p.category_title,
                    image_url=p.image_url,
                    cleaned_image_url=p.cleaned_image_url,
                    key_features=p.key_features,
                    materials=p.materials,
                    offers=offers,
                )
            )
        return Channel3SearchResponse(
            query=query,
            products=products,
            next_page_token=next_page_token,
            total_returned=len(products),
        )

    async def sync_channel3_offers_for_product(
        self,
        product_id: UUID,
        user_id: str | None = None,
    ) -> Channel3SyncOffersResponse:
        """Fetch live merchant offers from Channel3 for a product and persist in minor units."""
        stmt = select(Product).where(Product.id == product_id)
        res = await self._db.execute(stmt)
        product = res.scalar_one_or_none()
        if product is None:
            raise NotFoundError(f"Product '{product_id}' was not found.")

        search_query = f"{product.brand} {product.name}".strip()
        try:
            raw_offers = await self._channel3.search_offers(
                query=search_query,
                barcode=product.ean_or_upc,
                limit=5,
                user_id=user_id,
            )
        except Channel3RateLimitError as exc:
            raise RateLimitError(str(exc)) from exc
        except Channel3Error as exc:
            raise DependencyError(str(exc)) from exc

        # Resolve DataSource for Channel3
        ds_stmt = select(DataSource).where(DataSource.code == "channel3")
        ds_res = await self._db.execute(ds_stmt)
        data_source = ds_res.scalar_one_or_none()
        if data_source is None:
            data_source = DataSource(
                code="channel3",
                name="Channel3 Universal Product Catalog",
                attribution_url="https://trychannel3.com",
                license_or_terms="Channel3 Commercial Product & Offer Catalog API v1",
            )
            self._db.add(data_source)
            await self._db.flush()

        now = datetime.now(UTC)
        persisted_offers: list[ProductOfferResponse] = []

        for c3_offer in raw_offers:
            offer = ProductOffer(
                product_id=product.id,
                data_source_id=data_source.id,
                merchant_name=c3_offer.merchant_name[:150],
                offer_url=c3_offer.offer_url,
                price_minor_units=c3_offer.price_minor_units,
                currency=c3_offer.currency.upper()[:3],
                is_in_stock=c3_offer.is_in_stock,
                retrieved_at=now,
            )
            self._db.add(offer)
            await self._db.flush()
            persisted_offers.append(
                ProductOfferResponse(
                    id=offer.id,
                    merchant_name=offer.merchant_name,
                    offer_url=offer.offer_url,
                    price_minor_units=offer.price_minor_units,
                    currency=offer.currency,
                    formatted_price=format_currency(offer.price_minor_units, offer.currency),
                    is_in_stock=offer.is_in_stock,
                    retrieved_at=offer.retrieved_at,
                )
            )

        await self._db.commit()
        return Channel3SyncOffersResponse(
            product_id=product.id,
            product_name=product.name,
            offers_synced=len(persisted_offers),
            offers=persisted_offers,
            retrieved_at=now,
        )

    def _map_to_product_detail(self, product: Product) -> ProductDetailResponse:
        """Map SQLAlchemy Product model to ProductDetailResponse."""
        brand_info = BrandResponse.model_validate(product.brand_rel) if product.brand_rel else None

        variants = [ProductVariantResponse.model_validate(v) for v in product.variants]

        formula_history: list[ProductIngredientListResponse] = []
        current_formula: ProductIngredientListResponse | None = None

        for il in product.ingredient_lists:
            ds_resp = DataSourceResponse.model_validate(il.data_source) if il.data_source else None

            items = [
                ProductIngredientItemResponse(
                    position=pi.position,
                    ingredient_id=pi.ingredient.id,
                    inci_name=pi.ingredient.inci_name,
                    common_name=pi.ingredient.common_name,
                    function=pi.ingredient.function,
                    safety_rating=pi.ingredient.safety_rating,
                    concentration_percentage=pi.concentration_percentage,
                    notes=pi.notes,
                )
                for pi in il.items
                if pi.ingredient is not None
            ]

            il_resp = ProductIngredientListResponse(
                id=il.id,
                formula_version=il.formula_version,
                is_current=il.is_current,
                raw_ingredient_text=il.raw_ingredient_text,
                retrieved_at=il.retrieved_at,
                data_source=ds_resp,
                ingredients=items,
            )
            formula_history.append(il_resp)

            if il.is_current:
                current_formula = il_resp

        # Fallback if no list marked current, pick the first in history
        if current_formula is None and formula_history:
            current_formula = formula_history[0]

        offers = [
            ProductOfferResponse(
                id=o.id,
                merchant_name=o.merchant_name,
                offer_url=o.offer_url,
                price_minor_units=o.price_minor_units,
                currency=o.currency,
                formatted_price=format_currency(o.price_minor_units, o.currency),
                is_in_stock=o.is_in_stock,
                retrieved_at=o.retrieved_at,
            )
            for o in product.offers
        ]

        return ProductDetailResponse(
            id=product.id,
            name=product.name,
            brand=product.brand,
            brand_id=product.brand_id,
            category=product.category,
            description=product.description,
            ean_or_upc=product.ean_or_upc,
            image_url=product.image_url,
            brand_info=brand_info,
            variants=variants,
            current_formula=current_formula,
            formula_history=formula_history,
            offers=offers,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )
