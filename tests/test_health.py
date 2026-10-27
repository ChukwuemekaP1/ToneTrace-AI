"""Tests for liveness, readiness, and safe integration health endpoints."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import IntegrationState, Settings, get_settings
from app.schemas.health import DependencyStatus


@pytest.mark.asyncio
async def test_liveness_probe(client: httpx.AsyncClient):
    """Verify /health/live returns fast 200 OK without probing external dependencies."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data
    assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_versioned_liveness_probe(client: httpx.AsyncClient):
    """Verify versioned /api/v1/health/live also works consistently."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_probe_healthy(client: httpx.AsyncClient):
    """Verify /health/ready returns 200 when all required dependencies are healthy."""
    with patch("app.api.routes.health.check_db_health", new_callable=AsyncMock) as mock_db:
        mock_db.return_value = (True, 1.45, None)

        response = await client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["dependencies"]["database"]["status"] == "healthy"
        assert data["dependencies"]["database"]["required"] is True
        assert data["dependencies"]["database"]["latency_ms"] == 1.45


@pytest.mark.asyncio
async def test_readiness_probe_required_failure(client: httpx.AsyncClient):
    """Verify /health/ready returns 503 when the required database dependency is unhealthy."""
    with patch("app.api.routes.health.check_db_health", new_callable=AsyncMock) as mock_db:
        mock_db.return_value = (False, 25.0, "Database probe failed: Connection refused")

        response = await client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["dependencies"]["database"]["status"] == "unhealthy"
        assert data["dependencies"]["database"]["required"] is True
        assert "Connection refused" in data["dependencies"]["database"]["details"]


@pytest.mark.asyncio
async def test_readiness_probe_optional_degraded(client: httpx.AsyncClient, app):
    """Verify /health/ready returns 200 degraded when optional Elasticsearch fails."""
    test_settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ELASTICSEARCH_ENABLED=True,
        ELASTICSEARCH_URL="http://localhost:9200",
    )
    app.dependency_overrides[get_settings] = lambda: test_settings

    with (
        patch("app.api.routes.health.check_db_health", new_callable=AsyncMock) as mock_db,
        patch("app.api.routes.health._probe_elasticsearch", new_callable=AsyncMock) as mock_es,
    ):
        mock_db.return_value = (True, 2.1, None)
        mock_es.return_value = DependencyStatus(
            name="elasticsearch",
            status="unhealthy",
            required=False,
            latency_ms=10.0,
            details="Connection refused",
        )

        response = await client.get("/health/ready")
        assert response.status_code == 200  # Remains 200 because ES is optional
        data = response.json()
        assert data["status"] == "degraded"
        assert data["dependencies"]["elasticsearch"]["status"] == "unhealthy"
        assert data["dependencies"]["elasticsearch"]["required"] is False


@pytest.mark.asyncio
async def test_integrations_status_safe_reporting(client: httpx.AsyncClient):
    """Verify /health/integrations safely reports state without leaking any secrets."""
    response = await client.get("/health/integrations")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    integrations = data["integrations"]

    expected_keys = [
        "database",
        "elasticsearch",
        "clerk_auth",
        "gemini_ai",
        "ocr",
        "product_catalog",
        "skin_analysis",
        "object_storage",
    ]
    for key in expected_keys:
        assert key in integrations
        item = integrations[key]
        assert "state" in item
        assert item["state"] in [s.value for s in IntegrationState]
        # Guarantee no secrets or keys leaked in description or fields
        assert "password" not in str(item).lower()
        assert "secret" not in str(item).lower()


@pytest.mark.asyncio
async def test_root_index(client: httpx.AsyncClient):
    """Verify root / index provides envelope with application metadata."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["name"] == "ToneTrace AI API"
    assert "version" in data["data"]
    assert "request_id" in data["meta"]
