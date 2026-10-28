"""Tests for Phase 9: My Shelf and Product Discovery.

Covers:
- Custom products and catalogue-linked products on My Shelf
- Shelf ownership isolation (a user can never read or mutate another user's shelf)
- Duplicate addition prevention (409 Conflict)
- Graceful handling of unavailable/deleted catalogue records
- Product reactions and suspected ingredient tracking
- Product discovery with Elasticsearch, Elasticsearch outages, and PostgreSQL fallback policy
- Filters, pagination, deterministic sorting, and commercial offer segregation
- Transparent, versioned rule-based recommendations and handling of incomplete ingredient data
- Grounded Gemini recommendation explanations traceable to retrieved source IDs
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.ai import get_llm_explanation_provider
from app.core.config import Settings, get_settings
from app.db.models import (
    Ingredient,
    IngredientEvidence,
    Product,
    ProductIngredient,
    ProductIngredientList,
    ProductOffer,
)
from app.providers.gemini import LLMExplanationProvider, LLMGenerationResult
from app.providers.search_provider import SearchProvider, get_search_provider
from app.schemas.ai_explanations import (
    GeminiStructuredExplanationPayload,
    StructuredFindingItem,
)


async def _register_and_login(
    client: httpx.AsyncClient,
    email: str,
) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "display_name": email.split("@")[0],
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_discovery_catalogue(
    test_session: AsyncSession,
) -> dict[str, object]:
    """Seed canonical products, ingredients, evidence, and offers in PostgreSQL."""
    niacinamide = Ingredient(
        inci_name="Niacinamide",
        common_name="Vitamin B3",
        aliases=["Nicotinamide"],
        function="brightening, barrier_support",
        description="Water-soluble amide of vitamin B3 studied for visible tone unevenness.",
        safety_rating="safe",
    )
    glycerin = Ingredient(
        inci_name="Glycerin",
        common_name="Glycerol",
        aliases=[],
        function="humectant",
        description="Classic humectant supporting stratum corneum hydration.",
        safety_rating="safe",
    )
    fragrance = Ingredient(
        inci_name="Parfum",
        common_name="Fragrance",
        aliases=["Aroma"],
        function="fragrance",
        description="Volatile aromatic blend that may trigger skin sensitivity.",
        safety_rating="moderate_hazard",
    )
    test_session.add_all([niacinamide, glycerin, fragrance])
    await test_session.flush()

    ev_niacinamide = IngredientEvidence(
        ingredient_id=niacinamide.id,
        evidence_category="published_research",
        topic_or_target="hyperpigmentation",
        evidence_direction="supportive",
        evidence_strength="moderate",
        study_type="rct",
        population_or_context="Topical cosmetic formulations (2%-5%) over 8 weeks",
        summary_statement=(
            "Controlled trials report reduced melanosome transfer and improved visible "
            "hyperpigmentation appearance with topical niacinamide."
        ),
        limitations_and_caveats="Abstract-level metadata; individual product vehicle varies.",
        author_or_reviewer="pubmed_importer",
        review_status="verified",
    )
    test_session.add(ev_niacinamide)
    await test_session.flush()

    prod_complete = Product(
        name="Brightening Niacinamide Serum",
        brand="DermaPure",
        category="serum",
        description="Lightweight daily serum formulated with Niacinamide and Glycerin.",
        full_ingredient_list="Aqua, Niacinamide, Glycerin",
        ean_or_upc="0099112233445",
    )
    prod_incomplete = Product(
        name="Mystery Unlisted Toner",
        brand="OpaqueBeauty",
        category="toner",
        description="Refreshing facial mist without published ingredient breakdown.",
        full_ingredient_list=None,
        ean_or_upc="0099112233446",
    )
    prod_irritant = Product(
        name="Perfumed Botanical Cream",
        brand="ScentLux",
        category="moisturizer",
        description="Rich scented facial moisturizer.",
        full_ingredient_list="Aqua, Glycerin, Parfum",
        ean_or_upc="0099112233447",
    )
    test_session.add_all([prod_complete, prod_incomplete, prod_irritant])
    await test_session.flush()

    il_complete = ProductIngredientList(
        product_id=prod_complete.id,
        formula_version="v1",
        is_current=True,
        raw_ingredient_text="Aqua, Niacinamide, Glycerin",
    )
    test_session.add(il_complete)
    await test_session.flush()

    test_session.add_all(
        [
            ProductIngredient(
                product_id=prod_complete.id,
                product_ingredient_list_id=il_complete.id,
                ingredient_id=niacinamide.id,
                position=1,
                concentration_percentage=None,  # Explicitly unknown concentration
            ),
            ProductIngredient(
                product_id=prod_complete.id,
                product_ingredient_list_id=il_complete.id,
                ingredient_id=glycerin.id,
                position=2,
                concentration_percentage=None,
            ),
            ProductIngredient(
                product_id=prod_irritant.id,
                ingredient_id=glycerin.id,
                position=1,
                concentration_percentage=None,
            ),
            ProductIngredient(
                product_id=prod_irritant.id,
                ingredient_id=fragrance.id,
                position=2,
                concentration_percentage=None,
            ),
        ]
    )

    offer = ProductOffer(
        product_id=prod_complete.id,
        merchant_name="DermaStore Direct",
        offer_url="https://example.com/dermapure-niacinamide",
        price_minor_units=1899,
        currency="USD",
        is_in_stock=True,
        retrieved_at=datetime.now(UTC),
    )
    test_session.add(offer)
    await test_session.commit()

    return {
        "niacinamide": niacinamide,
        "glycerin": glycerin,
        "fragrance": fragrance,
        "ev_niacinamide": ev_niacinamide,
        "prod_complete": prod_complete,
        "prod_incomplete": prod_incomplete,
        "prod_irritant": prod_irritant,
    }


@pytest.mark.asyncio
async def test_shelf_catalogue_linked_and_custom_products_and_duplicates(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
):
    """Verify catalogue-linked and custom products, sensitivity alerts, and duplicate rejection."""
    seeded = await _seed_discovery_catalogue(test_session)
    prod_irritant: Product = seeded["prod_irritant"]  # type: ignore[assignment]

    headers = await _register_and_login(client, "shelf_owner@example.com")

    # Add 'Parfum' to user sensitivities
    sens_resp = await client.post(
        "/api/v1/me/sensitivities",
        headers=headers,
        json={"ingredient_name": "Parfum", "severity": "high"},
    )
    assert sens_resp.status_code == 201

    # 1. Add catalogue-linked product
    add_cat_resp = await client.post(
        "/api/v1/me/shelf",
        headers=headers,
        json={
            "product_id": str(prod_irritant.id),
            "status": "in_use",
            "opened_at": "2026-10-01T08:00:00Z",
            "private_notes": "Patch testing on jawline only.",
        },
    )
    assert add_cat_resp.status_code == 201, add_cat_resp.text
    cat_item = add_cat_resp.json()["data"]
    assert cat_item["is_custom"] is False
    assert cat_item["catalogue_status"] == "catalogue_linked"
    assert cat_item["display_name"] == "Perfumed Botanical Cream"
    assert cat_item["ingredient_data_status"] == "complete"
    assert "Parfum" in cat_item["sensitivity_alerts"]
    assert cat_item["is_public"] is False
    assert cat_item["private_notes"] == "Patch testing on jawline only."

    # 2. Duplicate addition of same catalogue product -> 409 Conflict
    dup_cat_resp = await client.post(
        "/api/v1/me/shelf",
        headers=headers,
        json={"product_id": str(prod_irritant.id)},
    )
    assert dup_cat_resp.status_code == 409
    assert dup_cat_resp.json()["error"]["code"] == "CONFLICT"

    # 3. Add custom product not in public catalogue
    add_custom_resp = await client.post(
        "/api/v1/me/shelf",
        headers=headers,
        json={
            "custom_name": "Compounded Azelaic Gel",
            "custom_brand": "Local Derm Pharmacy",
            "custom_category": "treatment",
            "custom_ingredient_text": "Aqua, Azelaic Acid, Propylene Glycol",
            "status": "wishlist",
            "private_notes": "Recommended by clinic.",
        },
    )
    assert add_custom_resp.status_code == 201, add_custom_resp.text
    custom_item = add_custom_resp.json()["data"]
    assert custom_item["is_custom"] is True
    assert custom_item["catalogue_status"] == "custom_entry"
    assert custom_item["ingredient_data_status"] == "partial_text_only"
    assert custom_item["incomplete_ingredient_warning"] is not None

    # 4. Duplicate custom product (case-insensitive brand + name) -> 409 Conflict
    dup_custom_resp = await client.post(
        "/api/v1/me/shelf",
        headers=headers,
        json={
            "custom_name": "compounded azelaic gel",
            "custom_brand": "LOCAL DERM PHARMACY",
            "custom_category": "treatment",
        },
    )
    assert dup_custom_resp.status_code == 409


@pytest.mark.asyncio
async def test_shelf_ownership_isolation_update_reactions_and_delete(
    client: httpx.AsyncClient,
):
    """Verify strict shelf ownership isolation, reaction logging via PATCH, and deletion."""
    headers_a = await _register_and_login(client, "alice_shelf@example.com")
    headers_b = await _register_and_login(client, "bob_shelf@example.com")

    create_resp = await client.post(
        "/api/v1/me/shelf",
        headers=headers_a,
        json={
            "custom_name": "Evening Retinal Emulsion",
            "custom_brand": "ToneLab",
            "custom_category": "serum",
            "status": "in_use",
            "private_notes": "Strictly private note for Alice.",
        },
    )
    assert create_resp.status_code == 201
    item_id = create_resp.json()["data"]["id"]

    # Bob cannot read, update, or delete Alice's shelf item
    assert (await client.get(f"/api/v1/me/shelf/{item_id}", headers=headers_b)).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/me/shelf/{item_id}",
            headers=headers_b,
            json={"status": "finished"},
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/me/shelf/{item_id}", headers=headers_b)
    ).status_code == 404

    bob_list = await client.get("/api/v1/me/shelf", headers=headers_b)
    assert bob_list.status_code == 200
    assert bob_list.json()["data"]["total"] == 0

    # Alice updates her item and logs a reaction
    patch_resp = await client.patch(
        f"/api/v1/me/shelf/{item_id}",
        headers=headers_a,
        json={
            "status": "paused",
            "private_notes": "Paused after mild stinging around nasolabial fold.",
            "reaction": {
                "reaction_type": "stinging",
                "severity": "mild",
                "suspected_ingredient_names": ["Retinal"],
                "notes": "Occurred on night 3",
            },
        },
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()["data"]
    assert updated["status"] == "paused"
    assert len(updated["reactions"]) == 1
    assert updated["reactions"][0]["reaction_type"] == "stinging"
    assert updated["reactions"][0]["suspected_ingredient_names"] == ["Retinal"]

    # Alice deletes her item
    del_resp = await client.delete(f"/api/v1/me/shelf/{item_id}", headers=headers_a)
    assert del_resp.status_code == 200
    assert (await client.get(f"/api/v1/me/shelf/{item_id}", headers=headers_a)).status_code == 404


@pytest.mark.asyncio
async def test_shelf_handles_unavailable_catalogue_data_gracefully(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
):
    """Verify shelf items remain readable and honest if a linked catalogue product is removed."""
    temp_product = Product(
        name="Limited Edition Barrier Balm",
        brand="EphemeralSkin",
        category="moisturizer",
        description="Seasonal balm.",
    )
    test_session.add(temp_product)
    await test_session.commit()

    headers = await _register_and_login(client, "unavail_cat@example.com")
    add_resp = await client.post(
        "/api/v1/me/shelf",
        headers=headers,
        json={
            "product_id": str(temp_product.id),
            "status": "in_use",
            "private_notes": "Bought in winter.",
        },
    )
    assert add_resp.status_code == 201
    shelf_item_id = add_resp.json()["data"]["id"]

    # Remove the catalogue product from PostgreSQL (simulating unavailable/retired catalogue record)
    await test_session.execute(delete(Product).where(Product.id == temp_product.id))
    await test_session.commit()

    get_resp = await client.get(f"/api/v1/me/shelf/{shelf_item_id}", headers=headers)
    assert get_resp.status_code == 200
    data = get_resp.json()["data"]
    assert data["catalogue_status"] == "catalogue_unavailable"
    assert data["display_name"] == "Limited Edition Barrier Balm"
    assert data["display_brand"] == "EphemeralSkin"
    assert data["ingredient_data_status"] == "missing"
    assert data["incomplete_ingredient_warning"] is not None


@pytest.mark.asyncio
async def test_discovery_incomplete_ingredients_honesty_and_recommendation_rules(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
    app,
):
    """Verify discovery rules never treat missing ingredients as safe and segregate offers."""
    seeded = await _seed_discovery_catalogue(test_session)
    prod_complete: Product = seeded["prod_complete"]  # type: ignore[assignment]
    prod_incomplete: Product = seeded["prod_incomplete"]  # type: ignore[assignment]

    test_settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ELASTICSEARCH_ENABLED=False,
        ELASTICSEARCH_FALLBACK_TO_DB=True,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        headers = await _register_and_login(client, "discover_rules@example.com")

        # Configure user's skin profile & sensitivity to 'Parfum'
        await client.put(
            "/api/v1/me/skin-profile",
            headers=headers,
            json={
                "skin_type": "combination",
                "skin_concerns": ["hyperpigmentation"],
                "skin_goals": ["brightening"],
            },
        )
        await client.post(
            "/api/v1/me/sensitivities",
            headers=headers,
            json={"ingredient_name": "Parfum", "severity": "moderate"},
        )

        # 1. Discover products (excludes 'prod_irritant' automatically because of 'Parfum')
        disc_resp = await client.get(
            "/api/v1/discovery/products?goal=hyperpigmentation&sort_by=suitability_desc",
            headers=headers,
        )
        assert disc_resp.status_code == 200, disc_resp.text
        disc_data = disc_resp.json()["data"]
        assert disc_data["rule_engine_version"] == "tonetrace-discovery-rules-v1.0"
        returned_ids = [item["product_id"] for item in disc_data["items"]]
        assert str(prod_complete.id) in returned_ids
        assert str(prod_incomplete.id) in returned_ids
        assert len(returned_ids) == 2

        by_id = {item["product_id"]: item for item in disc_data["items"]}
        complete_item = by_id[str(prod_complete.id)]
        incomplete_item = by_id[str(prod_incomplete.id)]

        # Complete product with evidence ranks higher and is 'recommended_fit'
        assert complete_item["recommendation"]["suitability_tier"] == "recommended_fit"
        assert complete_item["recommendation"]["matched_goal_ingredients"] == ["Niacinamide"]
        assert complete_item["lowest_offer_minor_units"] == 1899

        # Incomplete product is explicitly marked 'insufficient_ingredient_data'
        assert (
            incomplete_item["recommendation"]["suitability_tier"] == "insufficient_ingredient_data"
        )
        assert incomplete_item["recommendation"]["ingredient_data_status"] == "missing"
        assert incomplete_item["recommendation"]["missing_data_is_not_safety_proof"] is True
        r1_rule = next(
            r
            for r in incomplete_item["recommendation"]["rules_triggered"]
            if r["rule_id"] == "R1_INGREDIENT_DATA_COMPLETENESS"
        )
        assert r1_rule["outcome"] == "warning"
        assert "never treated as proof of safety" in r1_rule["explanation"].lower()

        # 2. Setting require_complete_ingredients=true filters out the incomplete product
        strict_resp = await client.get(
            "/api/v1/discovery/products?require_complete_ingredients=true",
            headers=headers,
        )
        assert strict_resp.status_code == 200
        strict_ids = [item["product_id"] for item in strict_resp.json()["data"]["items"]]
        assert strict_ids == [str(prod_complete.id)]
    finally:
        app.dependency_overrides.pop(get_settings, None)


@pytest.mark.asyncio
async def test_discovery_elasticsearch_outage_and_fallback_policy(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
    app,
):
    """Verify ES text search, 503 on outage when fallback disabled, and DB fallback when enabled."""
    seeded = await _seed_discovery_catalogue(test_session)
    prod_complete: Product = seeded["prod_complete"]  # type: ignore[assignment]
    headers = await _register_and_login(client, "es_policy@example.com")

    # 1. ES enabled and healthy -> uses 'elasticsearch' backend
    healthy_es = MagicMock(spec=SearchProvider)
    healthy_es.products_alias = "tonetrace_products"
    healthy_es.check_health.return_value = (True, "OK", 2.0)
    healthy_es.execute_search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_score": 4.2,
                    "_source": {
                        "id": str(prod_complete.id),
                        "name": prod_complete.name,
                        "brand": prod_complete.brand,
                        "category": prod_complete.category,
                        "description": prod_complete.description,
                        "full_ingredient_list": prod_complete.full_ingredient_list,
                        "ingredient_names": ["niacinamide", "glycerin"],
                    },
                }
            ],
        },
        "aggregations": {},
    }

    es_enabled_no_fallback = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ELASTICSEARCH_ENABLED=True,
        ELASTICSEARCH_FALLBACK_TO_DB=False,
    )
    app.dependency_overrides[get_settings] = lambda: es_enabled_no_fallback
    app.dependency_overrides[get_search_provider] = lambda: healthy_es
    try:
        res_ok = await client.get("/api/v1/discovery/products?q=Niacinamide", headers=headers)
        assert res_ok.status_code == 200
        assert res_ok.json()["data"]["search_backend_used"] == "elasticsearch"
        assert res_ok.json()["data"]["total"] == 1

        # 2. Simulate ES outage with ELASTICSEARCH_FALLBACK_TO_DB=False -> 503 DependencyError
        unhealthy_es = MagicMock(spec=SearchProvider)
        unhealthy_es.check_health.return_value = (False, "Connection timeout", 0.0)
        app.dependency_overrides[get_search_provider] = lambda: unhealthy_es

        res_503 = await client.get("/api/v1/discovery/products?q=Niacinamide", headers=headers)
        assert res_503.status_code == 503
        assert res_503.json()["error"]["code"] == "DEPENDENCY_ERROR"

        # 3. Simulate ES outage with ELASTICSEARCH_FALLBACK_TO_DB=True -> PostgreSQL fallback
        es_enabled_with_fallback = Settings(
            ENVIRONMENT="test",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            ELASTICSEARCH_ENABLED=True,
            ELASTICSEARCH_FALLBACK_TO_DB=True,
        )
        app.dependency_overrides[get_settings] = lambda: es_enabled_with_fallback
        res_fb = await client.get("/api/v1/discovery/products?q=Niacinamide", headers=headers)
        assert res_fb.status_code == 200
        fb_data = res_fb.json()["data"]
        assert fb_data["search_backend_used"] == "postgresql_fallback"
        assert fb_data["degraded_search_warning"] is not None
        assert fb_data["total"] == 1
        assert fb_data["items"][0]["product_id"] == str(prod_complete.id)
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_search_provider, None)


@pytest.mark.asyncio
async def test_discovery_product_detail_and_grounded_ai_explanation(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
    app,
):
    """Verify product detail endpoint, unknown concentration disclosure, and AI explanation."""
    seeded = await _seed_discovery_catalogue(test_session)
    prod_complete: Product = seeded["prod_complete"]  # type: ignore[assignment]
    niacinamide: Ingredient = seeded["niacinamide"]  # type: ignore[assignment]
    ev_niacinamide: IngredientEvidence = seeded["ev_niacinamide"]  # type: ignore[assignment]

    class DeterministicDiscoveryLLMProvider(LLMExplanationProvider):
        @property
        def name(self) -> str:
            return "mock-gemini"

        @property
        def model_name(self) -> str:
            return "gemini-3.5-flash-lite"

        @property
        def is_configured(self) -> bool:
            return True

        async def check_health(self) -> tuple[bool, str | None]:
            return True, "Ready"

        async def generate_structured_explanation(
            self,
            system_instruction: str,
            grounded_prompt: str,
            response_schema: dict[str, object],
        ) -> LLMGenerationResult:
            _ = (system_instruction, grounded_prompt, response_schema)
            payload = GeminiStructuredExplanationPayload(
                summary=(
                    "DermaPure Brightening Niacinamide Serum contains Niacinamide, which has "
                    "published RCT research relating to visible hyperpigmentation appearance."
                ),
                key_findings=[
                    StructuredFindingItem(
                        statement=(
                            "The formula includes Niacinamide, backed by controlled trial "
                            "evidence for visible hyperpigmentation support, though the exact "
                            "percentage in this product is not disclosed."
                        ),
                        epistemic_category="published_research",
                        evidence_strength="moderate",
                        cited_source_ids=[
                            f"prod:{prod_complete.id}",
                            f"ing:{niacinamide.id}",
                            f"ev:{ev_niacinamide.id}",
                        ],
                    )
                ],
                uncertainty_notes=["Exact Niacinamide concentration in this product is unknown."],
                requires_professional_care_escalation=False,
            )
            return LLMGenerationResult(
                raw_text=payload.model_dump_json(),
                provider=self.name,
                model=self.model_name,
                latency_ms=15.0,
            )

    app.dependency_overrides[get_llm_explanation_provider] = lambda: (
        DeterministicDiscoveryLLMProvider()
    )
    try:
        headers = await _register_and_login(client, "detail_ai@example.com")
        resp = await client.get(
            f"/api/v1/discovery/products/{prod_complete.id}"
            "?goal=hyperpigmentation&include_ai_explanation=true",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        detail = resp.json()["data"]
        assert detail["product_id"] == str(prod_complete.id)
        assert detail["ingredient_data_status"] == "complete"
        assert len(detail["ingredients"]) == 2
        assert detail["ingredients"][0]["inci_name"] == "Niacinamide"
        assert detail["ingredients"][0]["concentration_status"] == "unknown_order_only"
        assert detail["ingredients"][0]["concentration_percentage"] is None
        assert len(detail["commercial_offers"]) == 1
        assert (
            detail["commercial_offers"][0]["commercial_segregation_label"]
            == "commercial_offer_not_scientific_endorsement"
        )

        # Verify grounded AI explanation is attached and verified against retrieved source IDs
        ai_exp = detail["grounded_ai_explanation"]
        assert ai_exp is not None
        assert ai_exp["grounding_status"] == "verified"
        cited_ids = {ref["source_id"] for ref in ai_exp["source_references"]}
        assert f"prod:{prod_complete.id}" in cited_ids
        assert f"ing:{niacinamide.id}" in cited_ids
        assert f"ev:{ev_niacinamide.id}" in cited_ids
    finally:
        app.dependency_overrides.pop(get_llm_explanation_provider, None)
