"""Unit and integration tests for Elasticsearch Search Foundation and Outbox."""

import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest
from elasticsearch import ApiError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import DependencyError
from app.db.models import Ingredient, Product, ProductIngredient, SearchOutbox
from app.providers.search_provider import SearchProvider
from app.schemas.search import IngredientSearchQuery, ProductSearchQuery
from app.services.search_outbox_service import SearchOutboxService
from app.services.search_service import SearchService


@pytest.fixture(autouse=True)
def _enable_elasticsearch_for_search_tests(monkeypatch):
    """Enable Elasticsearch in settings specifically for search tests."""
    monkeypatch.setenv("ELASTICSEARCH_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_es_client():
    """Mocked official Elasticsearch client instance."""
    mock = MagicMock()
    mock.info.return_value = {
        "cluster_name": "test-cluster",
        "version": {"number": "8.15.3"},
    }
    mock.cluster.health.return_value = {"status": "green"}
    mock.indices.exists.return_value = True
    mock.indices.exists_alias.return_value = True
    return mock


@pytest.fixture
def search_provider_with_mock(mock_es_client):
    """SearchProvider instance bound to a mocked Elasticsearch client."""
    provider = SearchProvider()
    provider._client = mock_es_client
    return provider


# ------------------------------------------------------------------------------
# 1. SearchProvider Lifecycle & Mappings Tests
# ------------------------------------------------------------------------------


def test_search_provider_alias_naming():
    """Verify index and alias naming adhere to prefix conventions."""
    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite://",
        ELASTICSEARCH_INDEX_PREFIX="test_tt_",
    )
    provider = SearchProvider(settings=settings)
    assert provider.products_index_name == "test_tt_products_v1"
    assert provider.products_alias == "test_tt_products_current"
    assert provider.ingredients_index_name == "test_tt_ingredients_v1"
    assert provider.ingredients_alias == "test_tt_ingredients_current"


def test_search_provider_health_check(search_provider_with_mock):
    """Verify health check returns cluster name, version, status, and latency."""
    is_healthy, summary, latency = search_provider_with_mock.check_health()
    assert is_healthy is True
    assert "test-cluster" in summary
    assert "v8.15.3" in summary
    assert "green" in summary
    assert latency is not None


def test_search_provider_health_check_failure(search_provider_with_mock, mock_es_client):
    """Verify health check gracefully catches connection exceptions without leaking secrets."""
    mock_es_client.cluster.health.side_effect = ConnectionError("Connection refused")
    is_healthy, summary, latency = search_provider_with_mock.check_health()
    assert is_healthy is False
    assert "Connection failure" in summary


def test_ensure_indices_and_aliases_idempotence(search_provider_with_mock, mock_es_client):
    """Verify index creation is idempotent and binds aliases."""
    mock_es_client.indices.exists.return_value = False
    mock_es_client.indices.exists_alias.return_value = False

    res = search_provider_with_mock.ensure_indices_and_aliases()
    assert "products" in res
    assert "ingredients" in res
    assert mock_es_client.indices.create.call_count == 2
    assert mock_es_client.indices.put_alias.call_count == 2


def test_idempotent_delete_document(search_provider_with_mock, mock_es_client):
    """Verify document deletion is idempotent and ignores 404."""
    # 1. Normal delete
    mock_es_client.delete.return_value = {"result": "deleted"}
    assert search_provider_with_mock.delete_document("test_alias", "doc_123") is True

    # 2. 404 Not Found returns False without raising
    mock_es_client.delete.side_effect = ApiError(
        message="not_found",
        meta=MagicMock(status=404),
        body={},
    )
    assert search_provider_with_mock.delete_document("test_alias", "doc_nonexistent") is False


# ------------------------------------------------------------------------------
# 2. Bulk Indexing & Partial Failures
# ------------------------------------------------------------------------------


def test_bulk_indexing_partial_failures(search_provider_with_mock):
    """Verify bounded bulk processing captures partial errors per document."""
    documents = [
        {"id": "doc-1", "name": "Valid Product"},
        {"id": "doc-2", "name": "Invalid Product"},
    ]

    with patch("app.providers.search_provider.bulk") as mock_bulk:
        # Simulate partial failure: doc-1 succeeded, doc-2 failed
        mock_bulk.return_value = (
            1,
            [{"index": {"_id": "doc-2", "error": "mapper_parsing_exception"}}],
        )

        success_count, errors = search_provider_with_mock.bulk_index_documents(
            "test_alias",
            documents,
        )
        assert success_count == 1
        assert len(errors) == 1
        assert errors[0]["index"]["_id"] == "doc-2"


# ------------------------------------------------------------------------------
# 3. Transactional Outbox Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_outbox_transactional_enqueue(test_session: AsyncSession):
    """Verify outbox events are committed inside the database transaction."""
    entity_id = uuid.uuid4()
    event = SearchOutboxService.enqueue_sync_event(
        db=test_session,
        entity_type="product",
        entity_id=entity_id,
        action="index",
        payload={"name": "Hyaluronic Acid Serum", "brand": "The Ordinary"},
    )
    await test_session.commit()

    saved = await test_session.get(SearchOutbox, event.id)
    assert saved is not None
    assert saved.entity_id == entity_id
    assert saved.status == "pending"
    assert saved.retry_count == 0


@pytest.mark.asyncio
async def test_search_outbox_process_batch_success(
    test_session: AsyncSession,
    search_provider_with_mock,
):
    """Verify outbox processor marks succeeded events as completed."""
    entity_id = uuid.uuid4()
    SearchOutboxService.enqueue_sync_event(
        db=test_session,
        entity_type="product",
        entity_id=entity_id,
        action="index",
        payload={"name": "Niacinamide 10%", "brand": "The Ordinary"},
    )
    await test_session.commit()

    with patch.object(search_provider_with_mock, "bulk_index_documents", return_value=(1, [])):
        service = SearchOutboxService(
            db=test_session,
            search_provider=search_provider_with_mock,
        )
        summary = await service.process_outbox_batch(batch_size=10)

        assert summary["processed"] == 1
        assert summary["succeeded"] == 1
        assert summary["failed"] == 0

        # Verify state in DB
        stmt = select(SearchOutbox).where(SearchOutbox.entity_id == entity_id)
        saved = (await test_session.execute(stmt)).scalar_one()
        assert saved.status == "completed"
        assert saved.processed_at is not None
        assert saved.error_message is None


@pytest.mark.asyncio
async def test_search_outbox_retry_and_dead_letter_on_failure(
    test_session: AsyncSession,
    search_provider_with_mock,
):
    """Verify failing outbox events increment retry_count and enter failed status."""
    entity_id = uuid.uuid4()
    event = SearchOutboxService.enqueue_sync_event(
        db=test_session,
        entity_type="product",
        entity_id=entity_id,
        action="index",
        payload={"name": "Problematic Product"},
    )
    event.retry_count = 4  # 1 retry away from max_retries (5)
    await test_session.commit()

    # Simulate bulk failure for this doc
    error_resp = [{"index": {"_id": str(entity_id), "error": "ES mapping exception"}}]
    with patch.object(
        search_provider_with_mock,
        "bulk_index_documents",
        return_value=(0, error_resp),
    ):
        service = SearchOutboxService(
            db=test_session,
            search_provider=search_provider_with_mock,
        )
        summary = await service.process_outbox_batch(batch_size=10)

        assert summary["processed"] == 1
        assert summary["failed"] == 1

        await test_session.refresh(event)
        assert event.retry_count == 5
        assert event.status == "failed"
        assert "ES mapping exception" in event.error_message


# ------------------------------------------------------------------------------
# 4. Search Query Building & Execution Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_products_query_construction_and_facets(
    test_session: AsyncSession,
    search_provider_with_mock,
    mock_es_client,
):
    """Verify search queries construct multi_match, filters, sensitivity must_not, and facets."""
    mock_doc_id = str(uuid.uuid4())
    mock_es_client.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_id": mock_doc_id,
                    "_score": 4.5,
                    "_source": {
                        "id": mock_doc_id,
                        "name": "B-Hydra Intensive Hydration Serum",
                        "brand": "Drunk Elephant",
                        "category": "serum",
                        "description": "Replenishes skin moisture barrier.",
                        "full_ingredient_list": "Water, Sodium Hyaluronate, Panthenol...",
                        "ingredient_names": ["panthenol", "sodium hyaluronate"],
                        "image_url": "https://example.com/b-hydra.jpg",
                    },
                }
            ],
        },
        "aggregations": {
            "categories": {"buckets": [{"key": "serum", "doc_count": 1}]},
            "brands": {"buckets": [{"key": "Drunk Elephant", "doc_count": 1}]},
        },
    }

    service = SearchService(db=test_session, search_provider=search_provider_with_mock)
    query = ProductSearchQuery(
        q="Hydration",
        brand="Drunk Elephant",
        category="serum",
        exclude_ingredients=["Fragrance", "Essential Oils"],
        page=1,
        page_size=10,
    )

    results = await service.search_products(query)

    # Verify query payload sent to ES
    assert mock_es_client.search.called
    body = mock_es_client.search.call_args[1]["body"]
    bool_q = body["query"]["bool"]

    # Match query exists
    assert any("multi_match" in m for m in bool_q["must"])
    # Filters exist
    assert any("brand.keyword" in f.get("term", {}) for f in bool_q["filter"])
    assert any("category" in f.get("term", {}) for f in bool_q["filter"])
    # Exclusion exist
    assert any("ingredient_names" in n.get("terms", {}) for n in bool_q["must_not"])

    # Verify parsed hit
    assert results.total == 1
    assert len(results.items) == 1
    hit = results.items[0]
    assert hit.name == "B-Hydra Intensive Hydration Serum"
    assert hit.brand == "Drunk Elephant"
    assert hit.score == 4.5
    assert len(results.facets["categories"]) == 1


@pytest.mark.asyncio
async def test_search_ingredients_query(
    test_session: AsyncSession,
    search_provider_with_mock,
    mock_es_client,
):
    """Verify ingredient search executes and maps fields accurately."""
    mock_ing_id = str(uuid.uuid4())
    mock_es_client.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_id": mock_ing_id,
                    "_score": 5.0,
                    "_source": {
                        "id": mock_ing_id,
                        "inci_name": "NIACINAMIDE",
                        "common_name": "Vitamin B3",
                        "aliases": ["Nicotinamide"],
                        "function": "active",
                        "safety_rating": "safe",
                        "description": "Restores cellular energy and repairs DNA.",
                    },
                }
            ],
        },
        "aggregations": {
            "functions": {"buckets": [{"key": "active", "doc_count": 1}]},
            "safety_ratings": {"buckets": [{"key": "safe", "doc_count": 1}]},
        },
    }

    service = SearchService(db=test_session, search_provider=search_provider_with_mock)
    query = IngredientSearchQuery(q="Niacinamide", function="active", safety_rating="safe")
    results = await service.search_ingredients(query)

    assert results.total == 1
    ing = results.items[0]
    assert ing.inci_name == "NIACINAMIDE"
    assert ing.common_name == "Vitamin B3"
    assert ing.safety_rating == "safe"


# ------------------------------------------------------------------------------
# 5. Full Reindex from PostgreSQL Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_reindex_from_postgres(
    test_session: AsyncSession,
    search_provider_with_mock,
):
    """Verify reindex reads all records from PostgreSQL and dispatches bulk actions."""
    # Seed 1 ingredient and 1 product
    ing = Ingredient(
        inci_name="Ceramide NP",
        common_name="Ceramide 3",
        function="emollient",
        safety_rating="safe",
    )
    test_session.add(ing)
    await test_session.flush()

    prod = Product(
        name="Barrier Restoring Cream",
        brand="CeraVe",
        category="moisturizer",
        full_ingredient_list="Ceramide NP, Water",
    )
    test_session.add(prod)
    await test_session.flush()

    pi = ProductIngredient(
        product_id=prod.id,
        ingredient_id=ing.id,
        position=1,
    )
    test_session.add(pi)
    await test_session.commit()

    with patch.object(
        search_provider_with_mock,
        "bulk_index_documents",
        return_value=(1, []),
    ):
        service = SearchService(
            db=test_session,
            search_provider=search_provider_with_mock,
        )
        reindex_resp = await service.reindex_all_from_db()

        assert reindex_resp.status == "completed"
        assert reindex_resp.products_indexed == 1
        assert reindex_resp.ingredients_indexed == 1
        assert reindex_resp.duration_seconds >= 0


# ------------------------------------------------------------------------------
# 6. Failure & Disabled Fallback Behavior
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_fails_with_503_when_disabled(test_session: AsyncSession):
    """Verify searching when ELASTICSEARCH_ENABLED=False raises clear DependencyError."""
    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite://",
        ELASTICSEARCH_ENABLED=False,
    )
    service = SearchService(db=test_session, settings=settings)

    with pytest.raises(DependencyError) as exc_info:
        await service.search_products(ProductSearchQuery(q="test"))

    assert exc_info.value.status_code == 503
    assert "disabled" in exc_info.value.message


@pytest.mark.asyncio
async def test_search_fails_with_503_when_cluster_unavailable(
    test_session: AsyncSession,
    search_provider_with_mock,
):
    """Verify searching when cluster is offline raises 503 Service Unavailable."""
    with patch.object(
        search_provider_with_mock,
        "check_health",
        return_value=(False, "Connection timeout", None),
    ):
        service = SearchService(
            db=test_session,
            search_provider=search_provider_with_mock,
        )
        with pytest.raises(DependencyError) as exc_info:
            await service.search_products(ProductSearchQuery(q="test"))

        assert exc_info.value.status_code == 503
        assert "unavailable" in exc_info.value.message


# ------------------------------------------------------------------------------
# 7. Authenticated Search API Endpoints Tests
# ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_api_endpoints_integration(client: httpx.AsyncClient):
    """Verify /api/v1/search/products and /ingredients are authenticated and return envelopes."""
    # 1. Register test user to obtain auth token
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "search_tester@example.com",
            "password": "ValidPassword123!",
            "display_name": "Search Tester",
        },
    )
    token = reg_resp.json()["data"]["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Mock SearchService search_products
    mock_response = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "total_pages": 0,
        "facets": {},
    }
    with patch.object(
        SearchService,
        "search_products",
        return_value=mock_response,
    ):
        resp = await client.get("/api/v1/search/products?q=sunscreen", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["data"]["total"] == 0

    # 3. Unauthenticated request rejected
    unauth_resp = await client.get("/api/v1/search/products")
    assert unauth_resp.status_code == 401
