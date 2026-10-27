"""Tests for centralized error handling and response envelopes."""

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.main import create_app


@pytest.fixture
def error_test_app() -> FastAPI:
    """App with test routes raising various exception types."""
    settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )
    app = create_app(settings)

    @app.get("/test/not-found")
    async def route_not_found():
        raise NotFoundError("The requested skincare routine was not found.")

    @app.get("/test/conflict")
    async def route_conflict():
        raise ConflictError("A profile with this email already exists.")

    @app.get("/test/validation")
    async def route_validation():
        raise ValidationError("Invalid skin type provided.", details={"field": "skin_type"})

    @app.get("/test/crash")
    async def route_crash():
        # Raise unexpected internal error with simulated sensitive trace
        raise RuntimeError("Internal DB connection dropped: user=admin pass=supersecret")

    return app


@pytest.mark.asyncio
async def test_404_standard_envelope(error_test_app: FastAPI):
    """Verify non-existent route returns 404 in standardized ErrorResponse envelope."""
    transport = httpx.ASGITransport(app=error_test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/non-existent-endpoint-404")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NOT_FOUND"
        assert "request_id" in data["error"]
        assert data["error"]["request_id"] is not None


@pytest.mark.asyncio
async def test_custom_not_found_error(error_test_app: FastAPI):
    """Verify domain NotFoundError maps to 404 with custom code and message."""
    transport = httpx.ASGITransport(app=error_test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/test/not-found")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"
        assert "skincare routine was not found" in data["error"]["message"]


@pytest.mark.asyncio
async def test_conflict_error(error_test_app: FastAPI):
    """Verify domain ConflictError maps to 409."""
    transport = httpx.ASGITransport(app=error_test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/test/conflict")
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_validation_error(error_test_app: FastAPI):
    """Verify domain ValidationError maps to 422 with details."""
    transport = httpx.ASGITransport(app=error_test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/test/validation")
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["details"] == {"field": "skin_type"}


@pytest.mark.asyncio
async def test_unhandled_crash_never_leaks_secrets_or_stacktrace(error_test_app: FastAPI):
    """Verify unhandled exceptions return safe 500 without leaking stack traces or secrets."""
    transport = httpx.ASGITransport(app=error_test_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/test/crash")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        # Confirm sensitive strings from the exception message are NOT in the response
        assert "supersecret" not in response.text
        assert "admin" not in response.text
        assert "Traceback" not in response.text
        assert data["error"]["details"] is None
