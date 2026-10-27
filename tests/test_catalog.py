"""Tests for Phase 4: Product and Ingredient Catalogue.

Validates:
1. Open Beauty Facts adapter (success, missing fields, 404, 429 rate limit, 500 downtime).
2. Channel3 adapter contracts (unconfigured honest behavior, 401, 429, 200).
3. Product ingestion idempotency and outbox synchronization.
4. Formula versioning and preservation of historical formulas upon reformulation.
5. Commercial offers and price separation in integer minor units.
6. API routes and authorization boundaries.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.security import create_access_token
from app.db.models import (
    Brand,
    Ingredient,
    Product,
    ProductIngredient,
    ProductIngredientList,
    SearchOutbox,
    User,
)
from app.providers.channel3 import (
    Channel3Adapter,
    Channel3AuthenticationError,
    Channel3NotConfiguredError,
    Channel3RateLimitError,
    Channel3UnavailableError,
)
from app.providers.open_beauty_facts import (
    OpenBeautyFactsAdapter,
    OpenBeautyFactsProduct,
    OpenBeautyFactsRateLimitError,
    OpenBeautyFactsUnavailableError,
    ParsedIngredient,
)
from app.services.catalog_service import CatalogService, format_currency

# ============================================================================
# 1. Open Beauty Facts Provider Tests
# ============================================================================


@pytest.mark.asyncio
async def test_obf_fetch_product_success():
    """Verify Open Beauty Facts adapter correctly extracts fields without fabrication."""
    mock_payload = {
        "status": 1,
        "product": {
            "product_name": "Moisturizing Cream",
            "brands": "CeraVe, L'Oreal",
            "categories": "Moisturizer, Face Cream",
            "ingredients_text": "Aqua/Water, Glycerin, Cetearyl Alcohol, Ceramide NP",
            "image_url": "https://images.openbeautyfacts.org/cerave.jpg",
            "ingredients": [
                {"text": "Aqua/Water", "percent_estimate": 60.0},
                {"text": "Glycerin", "percent_estimate": 15.0},
                {"text": "Ceramide NP", "percent_estimate": None},
            ],
        },
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = httpx.Response(200, json=mock_payload, request=httpx.Request("GET", "https://test"))
    mock_client.get = AsyncMock(return_value=mock_resp)

    adapter = OpenBeautyFactsAdapter(client=mock_client)
    product = await adapter.fetch_product_by_barcode("3337875597371")

    assert product is not None
    assert product.barcode == "3337875597371"
    assert product.name == "Moisturizing Cream"
    assert product.brand == "CeraVe"
    assert product.category == "Moisturizer"
    assert product.image_url == "https://images.openbeautyfacts.org/cerave.jpg"
    assert len(product.ingredients) == 3
    assert product.ingredients[0].name == "Aqua/Water"
    assert product.ingredients[0].position == 1
    assert product.ingredients[0].percent_estimate == 60.0
    assert product.ingredients[2].percent_estimate is None
    assert "Open Beauty Facts" in product.attribution


@pytest.mark.asyncio
async def test_obf_not_found_returns_none():
    """Verify 404 or status 0 safely returns None."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    # Status 0 payload (not in database)
    mock_resp = httpx.Response(
        200,
        json={"status": 0, "status_verbose": "product not found"},
        request=httpx.Request("GET", "https://test"),
    )
    mock_client.get = AsyncMock(return_value=mock_resp)

    adapter = OpenBeautyFactsAdapter(client=mock_client)
    result = await adapter.fetch_product_by_barcode("0000000000000")
    assert result is None

    # HTTP 404
    mock_resp_404 = httpx.Response(404, request=httpx.Request("GET", "https://test"))
    mock_client.get = AsyncMock(return_value=mock_resp_404)
    result_404 = await adapter.fetch_product_by_barcode("0000000000001")
    assert result_404 is None


@pytest.mark.asyncio
async def test_obf_rate_limit_raises_error():
    """Verify HTTP 429 raises OpenBeautyFactsRateLimitError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = httpx.Response(429, request=httpx.Request("GET", "https://test"))
    mock_client.get = AsyncMock(return_value=mock_resp)

    adapter = OpenBeautyFactsAdapter(client=mock_client)
    with pytest.raises(OpenBeautyFactsRateLimitError):
        await adapter.fetch_product_by_barcode("3337875597371")


@pytest.mark.asyncio
async def test_obf_server_error_raises_unavailable():
    """Verify HTTP 500 raises OpenBeautyFactsUnavailableError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = httpx.Response(503, request=httpx.Request("GET", "https://test"))
    mock_client.get = AsyncMock(return_value=mock_resp)

    adapter = OpenBeautyFactsAdapter(client=mock_client)
    with pytest.raises(OpenBeautyFactsUnavailableError):
        await adapter.fetch_product_by_barcode("3337875597371")


# ============================================================================
# 2. Channel3 Provider Contract Tests
# ============================================================================


@pytest.mark.asyncio
async def test_channel3_unconfigured_behavior():
    """Verify Channel3 reports unconfigured and refuses queries when API key is missing."""
    adapter = Channel3Adapter(api_key=None)
    assert not adapter.is_configured
    healthy, msg = await adapter.check_health()
    assert not healthy
    assert "not configured" in msg

    with pytest.raises(Channel3NotConfiguredError):
        await adapter.search_offers("moisturizer")


@pytest.mark.asyncio
async def test_channel3_authentication_failure():
    """Verify Channel3 raises Channel3AuthenticationError on 401."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = httpx.Response(
        401, request=httpx.Request("POST", "https://api.trychannel3.com/v1/search")
    )
    mock_client.post = AsyncMock(return_value=mock_resp)

    adapter = Channel3Adapter(api_key="invalid_test_key", client=mock_client)
    assert adapter.is_configured

    with pytest.raises(Channel3AuthenticationError):
        await adapter.search_offers("retinol")


@pytest.mark.asyncio
async def test_channel3_rate_limit_and_server_error():
    """Verify Channel3 rate limits (429) and server errors (500)."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    adapter = Channel3Adapter(api_key="valid_test_key", client=mock_client)

    # 429
    mock_client.post = AsyncMock(
        return_value=httpx.Response(429, request=httpx.Request("POST", "https://test"))
    )
    with pytest.raises(Channel3RateLimitError):
        await adapter.search_offers("serum")

    # 500
    mock_client.post = AsyncMock(
        return_value=httpx.Response(500, request=httpx.Request("POST", "https://test"))
    )
    with pytest.raises(Channel3UnavailableError):
        await adapter.search_offers("serum")


@pytest.mark.asyncio
async def test_channel3_successful_offers_parsing():
    """Verify Channel3 parses product offers with price minor units."""
    mock_payload = {
        "results": [
            {
                "title": "Hydrating Cleanser 236ml",
                "merchant": "Ulta Beauty",
                "price": 16.99,
                "currency": "USD",
                "url": "https://ulta.com/cerave-cleanser",
                "in_stock": True,
                "barcode": "3337875597371",
            }
        ]
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(
        return_value=httpx.Response(
            200, json=mock_payload, request=httpx.Request("POST", "https://test")
        )
    )

    adapter = Channel3Adapter(api_key="valid_key", client=mock_client)
    offers = await adapter.search_offers("CeraVe Cleanser")

    assert len(offers) == 1
    offer = offers[0]
    assert offer.merchant_name == "Ulta Beauty"
    assert offer.price_minor_units == 1699
    assert offer.currency == "USD"
    assert offer.is_in_stock is True
    assert offer.barcode == "3337875597371"


# ============================================================================
# 3. Catalog Service & Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_ingest_from_barcode_creates_catalog_and_outbox(test_session):
    """Verify barcode ingestion populates brand, product, formula, and search outbox."""
    mock_obf = AsyncMock(spec=OpenBeautyFactsAdapter)
    mock_obf_product = OpenBeautyFactsProduct(
        barcode="1234567890123",
        name="Barrier Defense Fluid",
        brand="La Roche-Posay",
        category="Sunscreen",
        raw_ingredients_text="Water, Niacinamide, Glycerin, Silica",
        image_url="https://example.com/sunscreen.jpg",
        ingredients=[
            ParsedIngredient(name="Water", position=1, percent_estimate=65.0),
            ParsedIngredient(name="Niacinamide", position=2, percent_estimate=4.0),
            ParsedIngredient(name="Glycerin", position=3, percent_estimate=None),
        ],
    )
    mock_obf.fetch_product_by_barcode = AsyncMock(return_value=mock_obf_product)

    service = CatalogService(db=test_session, obf_adapter=mock_obf)
    resp = await service.ingest_from_barcode("1234567890123")

    assert resp.was_created is True
    product = resp.product
    assert product.name == "Barrier Defense Fluid"
    assert product.brand == "La Roche-Posay"
    assert product.ean_or_upc == "1234567890123"
    assert product.current_formula is not None
    assert product.current_formula.formula_version == "v1"
    assert len(product.current_formula.ingredients) == 3
    assert product.current_formula.ingredients[1].inci_name == "Niacinamide"
    assert product.current_formula.ingredients[1].concentration_percentage == 4.0

    # Verify SearchOutbox event was enqueued
    from sqlalchemy import select

    outbox_stmt = select(SearchOutbox).where(SearchOutbox.entity_id == product.id)
    outbox_res = await test_session.execute(outbox_stmt)
    event = outbox_res.scalar_one_or_none()
    assert event is not None
    assert event.entity_type == "product"
    assert event.action == "index"
    assert event.status == "pending"


@pytest.mark.asyncio
async def test_ingest_barcode_idempotence(test_session):
    """Verify ingesting the same barcode twice returns existing record without duplication."""
    mock_obf = AsyncMock(spec=OpenBeautyFactsAdapter)
    mock_obf.fetch_product_by_barcode = AsyncMock(
        return_value=OpenBeautyFactsProduct(
            barcode="9998887776665",
            name="Gentle Gel Cleanser",
            brand="The Ordinary",
            category="Cleanser",
            raw_ingredients_text="Aqua, Coco-Betaine",
            ingredients=[
                ParsedIngredient(name="Aqua", position=1),
                ParsedIngredient(name="Coco-Betaine", position=2),
            ],
        )
    )

    service = CatalogService(db=test_session, obf_adapter=mock_obf)
    resp1 = await service.ingest_from_barcode("9998887776665")
    assert resp1.was_created is True

    # Ingest again
    resp2 = await service.ingest_from_barcode("9998887776665")
    assert resp2.was_created is False
    assert resp2.product.id == resp1.product.id
    # Upstream adapter should not be called second time
    assert mock_obf.fetch_product_by_barcode.call_count == 1


@pytest.mark.asyncio
async def test_formula_reformulation_preserves_history(test_session):
    """Verify reformulation records new formula v2 while preserving historical v1 formula."""
    mock_obf = AsyncMock(spec=OpenBeautyFactsAdapter)
    mock_obf.fetch_product_by_barcode = AsyncMock(
        return_value=OpenBeautyFactsProduct(
            barcode="5554443332221",
            name="Super Glow Serum",
            brand="Paula's Choice",
            category="Serum",
            raw_ingredients_text="Water, Vitamin C 15%, Ferulic Acid",
            ingredients=[
                ParsedIngredient(name="Water", position=1),
                ParsedIngredient(name="Ascorbic Acid", position=2),
            ],
        )
    )

    service = CatalogService(db=test_session, obf_adapter=mock_obf)
    ingest_res = await service.ingest_from_barcode("5554443332221")
    product_id = ingest_res.product.id

    # Record a 2024 reformulation with new ingredient
    reform_res = await service.add_formula_reformulation(
        product_id=product_id,
        formula_version="2024-reformulation",
        raw_ingredient_text="Water, Vitamin C 15%, Ferulic Acid, Ergothioneine",
        ingredient_names=["Water", "Ascorbic Acid", "Ferulic Acid", "Ergothioneine"],
    )

    assert reform_res.formula_version == "2024-reformulation"
    assert reform_res.is_current is True
    assert len(reform_res.ingredients) == 4

    # Fetch product detail
    product_detail = await service.get_product(product_id)
    assert len(product_detail.formula_history) == 2
    assert product_detail.current_formula.formula_version == "2024-reformulation"

    # Prior formula v1 is preserved
    old_formula = next(f for f in product_detail.formula_history if f.formula_version == "v1")
    assert old_formula.is_current is False
    assert len(old_formula.ingredients) == 2


@pytest.mark.asyncio
async def test_commercial_offers_and_minor_units(test_session):
    """Verify commercial offers store money in integer minor units and format properly."""
    # Create test product
    brand = Brand(name="Glossier", slug="glossier")
    test_session.add(brand)
    await test_session.flush()

    prod = Product(
        name="Milky Jelly Cleanser",
        brand="Glossier",
        brand_id=brand.id,
        category="cleanser",
        ean_or_upc="1112223334445",
    )
    test_session.add(prod)
    await test_session.commit()

    service = CatalogService(db=test_session)
    offer = await service.record_product_offer(
        product_id=prod.id,
        merchant_name="Sephora",
        price_minor_units=1900,  # $19.00
        currency="USD",
        offer_url="https://sephora.com/milky-jelly",
        is_in_stock=True,
    )

    assert offer.price_minor_units == 1900
    assert offer.currency == "USD"
    assert offer.formatted_price == "$19.00"

    # Test format currency helper
    assert format_currency(2450, "USD") == "$24.50"
    assert format_currency(1800, "EUR") == "€18.00"
    assert format_currency(1500, "GBP") == "£15.00"


# ============================================================================
# 4. API Endpoints & Auth Guard Tests
# ============================================================================


@pytest.mark.asyncio
async def test_api_get_product_endpoints(client: httpx.AsyncClient, test_session):
    """Test GET /api/v1/products/{id} and /api/v1/products/barcode/{barcode}."""
    brand = Brand(name="SkinCeuticals", slug="skinceuticals")
    test_session.add(brand)
    await test_session.flush()

    prod = Product(
        name="C E Ferulic",
        brand="SkinCeuticals",
        brand_id=brand.id,
        category="Serum",
        ean_or_upc="3606000516315",
    )
    test_session.add(prod)
    await test_session.commit()

    # By ID
    res1 = await client.get(f"/api/v1/products/{prod.id}")
    assert res1.status_code == 200
    data1 = res1.json()["data"]
    assert data1["name"] == "C E Ferulic"
    assert data1["brand"] == "SkinCeuticals"

    # By Barcode
    res2 = await client.get("/api/v1/products/barcode/3606000516315")
    assert res2.status_code == 200
    data2 = res2.json()["data"]
    assert data2["id"] == str(prod.id)

    # Unknown barcode returns 404 standard envelope
    res3 = await client.get("/api/v1/products/barcode/0000000000000")
    assert res3.status_code == 404
    assert res3.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_api_ingest_barcode_requires_auth(client: httpx.AsyncClient, test_session):
    """Verify POST /api/v1/products/ingest/barcode/{barcode} requires active user authentication."""
    # Unauthenticated request fails with 401
    res = await client.post("/api/v1/products/ingest/barcode/1234567890123")
    assert res.status_code == 401

    # Authenticated user succeeds
    user = User(
        email="chemist@tonetrace.app",
        password_hash="fakehash",
        account_status="active",
    )
    test_session.add(user)
    await test_session.commit()

    token = create_access_token(user_id=user.id)
    headers = {"Authorization": f"Bearer {token}"}

    with patch.object(
        OpenBeautyFactsAdapter,
        "fetch_product_by_barcode",
        return_value=OpenBeautyFactsProduct(
            barcode="7778889990001",
            name="Hydra-Light Cream",
            brand="Biossance",
            category="Moisturizer",
            raw_ingredients_text="Squalane, Water",
            ingredients=[
                ParsedIngredient(name="Squalane", position=1),
                ParsedIngredient(name="Water", position=2),
            ],
        ),
    ):
        res_auth = await client.post(
            "/api/v1/products/ingest/barcode/7778889990001",
            headers=headers,
        )
        assert res_auth.status_code == 200
        data = res_auth.json()["data"]
        assert data["was_created"] is True
        assert data["product"]["name"] == "Hydra-Light Cream"
        assert data["product"]["brand"] == "Biossance"


@pytest.mark.asyncio
async def test_api_get_product_ingredients(client: httpx.AsyncClient, test_session):
    """Test GET /api/v1/products/{product_id}/ingredients."""
    brand = Brand(name="Youth To The People", slug="yttp")
    test_session.add(brand)
    await test_session.flush()

    prod = Product(
        name="Superfood Cleanser",
        brand="Youth To The People",
        brand_id=brand.id,
        category="Cleanser",
    )
    test_session.add(prod)
    await test_session.flush()

    il = ProductIngredientList(product_id=prod.id, formula_version="v1", is_current=True)
    test_session.add(il)
    await test_session.flush()

    ing = Ingredient(inci_name="Kale Extract", common_name="Kale", safety_rating="safe")
    test_session.add(ing)
    await test_session.flush()

    pi = ProductIngredient(
        product_id=prod.id,
        product_ingredient_list_id=il.id,
        ingredient_id=ing.id,
        position=1,
    )
    test_session.add(pi)
    await test_session.commit()

    res = await client.get(f"/api/v1/products/{prod.id}/ingredients")
    assert res.status_code == 200
    items = res.json()["data"]
    assert len(items) == 1
    assert items[0]["inci_name"] == "Kale Extract"
    assert items[0]["position"] == 1


@pytest.mark.asyncio
async def test_api_get_ingredient(client: httpx.AsyncClient, test_session):
    """Test GET /api/v1/ingredients/{ingredient_id}."""
    ing = Ingredient(
        inci_name="Tocopherol",
        common_name="Vitamin E",
        function="Antioxidant",
        safety_rating="safe",
        aliases=["Alpha-Tocopherol"],
    )
    test_session.add(ing)
    await test_session.commit()

    res = await client.get(f"/api/v1/ingredients/{ing.id}")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["inci_name"] == "Tocopherol"
    assert data["common_name"] == "Vitamin E"
    assert "Alpha-Tocopherol" in data["aliases"]


@pytest.mark.asyncio
async def test_api_reformulate_and_add_offer(client: httpx.AsyncClient, test_session):
    """Test POST /api/v1/products/{id}/reformulate and POST /api/v1/products/{id}/offers."""
    user = User(email="formulator@tonetrace.app", password_hash="hash", account_status="active")
    test_session.add(user)
    brand = Brand(name="KraveBeauty", slug="kravebeauty")
    test_session.add(brand)
    await test_session.flush()

    prod = Product(
        name="Great Barrier Relief",
        brand="KraveBeauty",
        brand_id=brand.id,
        category="Serum",
    )
    test_session.add(prod)
    await test_session.flush()

    il_v1 = ProductIngredientList(product_id=prod.id, formula_version="v1", is_current=True)
    test_session.add(il_v1)
    await test_session.commit()

    token = create_access_token(user_id=user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Reformulate to v2
    reform_payload = {
        "formula_version": "v2",
        "raw_ingredient_text": "Tamanu Oil, Ceramides, Rosehip Seed Oil",
        "ingredient_names": ["Tamanu Oil", "Ceramide NP", "Rosehip Seed Oil"],
        "data_source_code": "krave_official",
    }
    reform_res = await client.post(
        f"/api/v1/products/{prod.id}/reformulate",
        json=reform_payload,
        headers=headers,
    )
    assert reform_res.status_code == 201
    reform_data = reform_res.json()["data"]
    assert reform_data["formula_version"] == "v2"
    assert reform_data["is_current"] is True
    assert len(reform_data["ingredients"]) == 3

    # Duplicate formula version rejected with 409
    dup_res = await client.post(
        f"/api/v1/products/{prod.id}/reformulate",
        json=reform_payload,
        headers=headers,
    )
    assert dup_res.status_code == 409

    # 2. Add commercial offer
    offer_payload = {
        "merchant_name": "Krave Beauty Official",
        "price_minor_units": 2800,  # $28.00
        "currency": "USD",
        "offer_url": "https://kravebeauty.com/gbr",
        "is_in_stock": True,
    }
    offer_res = await client.post(
        f"/api/v1/products/{prod.id}/offers",
        json=offer_payload,
        headers=headers,
    )
    assert offer_res.status_code == 201
    offer_data = offer_res.json()["data"]
    assert offer_data["merchant_name"] == "Krave Beauty Official"
    assert offer_data["price_minor_units"] == 2800
    assert offer_data["formatted_price"] == "$28.00"
    assert offer_data["is_in_stock"] is True
