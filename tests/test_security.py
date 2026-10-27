"""Tests for security controls, cryptographic primitives, JWT claims, and rate limiting."""

from datetime import timedelta

import httpx
import pytest
from fastapi import Depends, FastAPI

from app.core.config import EnvironmentType, Settings, get_settings
from app.core.errors import AuthenticationError, RateLimitError, register_error_handlers
from app.core.security import (
    InMemoryRateLimiter,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models import User


def test_argon2id_password_hashing():
    """Verify passwords are hashed with Argon2id and verified in constant time."""
    password = "CorrectHorseBatteryStaple123!"
    hashed = hash_password(password)

    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_access_token_creation_and_decoding():
    """Verify JWT access tokens contain standard claims (sub, iss, aud, exp, jti)."""
    user_id = "018f3a3e-4d2b-7c5e-9a1b-3c4d5e6f7a8b"
    token = create_access_token(user_id=user_id, expires_delta=timedelta(minutes=10))

    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["iss"] == "tonetrace-auth"
    assert payload["aud"] == "tonetrace-api"
    assert "exp" in payload
    assert "jti" in payload


def test_jwt_expired_token_rejected():
    """Verify expired JWT tokens raise AuthenticationError."""
    user_id = "018f3a3e-4d2b-7c5e-9a1b-3c4d5e6f7a8b"
    expired_token = create_access_token(user_id=user_id, expires_delta=timedelta(seconds=-10))

    with pytest.raises(AuthenticationError, match="Access token has expired"):
        decode_access_token(expired_token)


def test_jwt_tampered_token_rejected():
    """Verify tampered or invalid signature raises AuthenticationError."""
    user_id = "018f3a3e-4d2b-7c5e-9a1b-3c4d5e6f7a8b"
    valid_token = create_access_token(user_id=user_id)
    tampered_token = valid_token[:-4] + "abcd"

    with pytest.raises(AuthenticationError, match="Invalid access token"):
        decode_access_token(tampered_token)


def test_refresh_token_generation_and_hashing():
    """Verify refresh tokens are high-entropy and stored only as SHA-256 hashes."""
    token1 = generate_refresh_token()
    token2 = generate_refresh_token()

    assert len(token1) >= 40
    assert token1 != token2

    hash1 = hash_token(token1)
    assert len(hash1) == 64  # SHA-256 hex digest length
    assert hash1 != token1
    assert hash_token(token1) == hash1


@pytest.mark.asyncio
async def test_in_memory_rate_limiter():
    """Verify sliding-window rate limiter blocks excessive requests."""
    limiter = InMemoryRateLimiter(requests_per_minute=3)
    key = "test_client_ip"

    # First 3 should succeed
    for _ in range(3):
        await limiter.check_rate_limit(key, enabled=True)

    # 4th should raise RateLimitError
    with pytest.raises(RateLimitError):
        await limiter.check_rate_limit(key, enabled=True)

    # Disabled limiter allows unlimited
    for _ in range(5):
        await limiter.check_rate_limit(key, enabled=False)


@pytest.mark.asyncio
async def test_client_supplied_user_id_rejected_in_production():
    """Verify client-supplied user ID is ALWAYS rejected in production environment."""
    from app.core.security import get_current_user

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/protected")
    async def protected_route(user: User = Depends(get_current_user)):
        return {"user_id": str(user.id)}

    settings = Settings(
        ENVIRONMENT=EnvironmentType.PRODUCTION,
        ALLOW_DEV_AUTH_BYPASS=False,
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        AUTH_JWT_SECRET="production-super-secret-key-at-least-32-chars-long-12345",
    )
    app.dependency_overrides[get_settings] = lambda: settings

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/protected", headers={"X-User-ID": "target_user_123"})
        assert response.status_code == 401
        assert "forbidden" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_request_id_propagation(client: httpx.AsyncClient):
    """Verify incoming X-Request-ID header is echoed back on the response."""
    custom_req_id = "trace-test-uuid-987654321"
    response = await client.get("/health/live", headers={"X-Request-ID": custom_req_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_req_id


@pytest.mark.asyncio
async def test_cors_headers_restricted(client: httpx.AsyncClient):
    """Verify CORS preflight restricts to configured origins."""
    # Preflight from allowed origin
    response = await client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Preflight from disallowed origin
    disallowed_resp = await client.options(
        "/health/live",
        headers={
            "Origin": "http://evil-attacker.site",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert disallowed_resp.headers.get("access-control-allow-origin") != "http://evil-attacker.site"
