"""Integration tests for first-party authentication.

Tests registration, login, rotation, replay detection, and logout.
"""

import httpx
import pytest

from app.core.security import auth_rate_limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Ensure in-memory rate limiter is reset before each auth test."""
    auth_rate_limiter.reset()


@pytest.mark.asyncio
async def test_user_registration_success(client: httpx.AsyncClient):
    """Verify user registration returns 201 Created and an authenticated session."""
    payload = {
        "email": "skincare_lover@example.com",
        "password": "SuperSecretSkincare123!",
        "display_name": "Glow Explorer",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    data = response.json()["data"]
    assert data["user"]["email"] == "skincare_lover@example.com"
    assert data["user"]["account_status"] == "active"
    assert data["user"]["is_email_verified"] is False
    assert "password_hash" not in data["user"]

    assert data["tokens"]["access_token"]
    assert data["tokens"]["refresh_token"]
    assert data["tokens"]["token_type"] == "Bearer"
    assert data["tokens"]["expires_in"] == 15 * 60


@pytest.mark.asyncio
async def test_user_registration_duplicate_email_conflict(client: httpx.AsyncClient):
    """Verify registering with an existing email returns 409 Conflict."""
    payload = {
        "email": "duplicate@example.com",
        "password": "Password12345!",
        "display_name": "Original User",
    }
    res1 = await client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    # Second registration with uppercase variant to verify normalization
    dup_payload = {
        "email": "DUPLICATE@example.com",
        "password": "AnotherPassword123!",
        "display_name": "Imposter",
    }
    res2 = await client.post("/api/v1/auth/register", json=dup_payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["error"]["message"]


@pytest.mark.asyncio
async def test_user_registration_short_password_rejected(client: httpx.AsyncClient):
    """Verify registration rejects passwords shorter than configured minimum length."""
    payload = {
        "email": "short_pwd@example.com",
        "password": "short",
        "display_name": "Short Pwd",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_user_login_success(client: httpx.AsyncClient):
    """Verify credentials login returns valid access and refresh tokens."""
    # Register user
    reg_payload = {
        "email": "login_test@example.com",
        "password": "PasswordSecure123!",
        "display_name": "Tester",
    }
    await client.post("/api/v1/auth/register", json=reg_payload)

    # Login
    login_payload = {
        "email": "login_test@example.com",
        "password": "PasswordSecure123!",
        "device_label": "iPhone 15 Pro",
    }
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["user"]["email"] == "login_test@example.com"
    assert data["tokens"]["access_token"]
    assert data["tokens"]["refresh_token"]


@pytest.mark.asyncio
async def test_user_login_invalid_credentials(client: httpx.AsyncClient):
    """Verify incorrect password returns 401 Unauthorized without leaking account existence."""
    # Register user
    reg_payload = {
        "email": "victim@example.com",
        "password": "ValidPassword123!",
        "display_name": "Victim",
    }
    await client.post("/api/v1/auth/register", json=reg_payload)

    # Wrong password
    bad_pass_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "victim@example.com", "password": "WrongPassword999!"},
    )
    assert bad_pass_resp.status_code == 401
    assert "Invalid email or password" in bad_pass_resp.json()["error"]["message"]

    # Unknown user
    unknown_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "WrongPassword999!"},
    )
    assert unknown_resp.status_code == 401
    assert "Invalid email or password" in unknown_resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_replay_detection(client: httpx.AsyncClient):
    """Verify refresh token rotation and session family termination upon replay."""
    # 1. Register
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rotator@example.com",
            "password": "RotateSecure123!",
            "display_name": "Token Rotator",
        },
    )
    r1_tokens = reg_resp.json()["data"]["tokens"]
    old_refresh = r1_tokens["refresh_token"]

    # 2. Rotate token
    rotate_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert rotate_resp.status_code == 200
    new_tokens = rotate_resp.json()["data"]
    new_refresh = new_tokens["refresh_token"]
    assert new_refresh != old_refresh

    # 3. REPLAY ATTACK: Attacker or buggy client replays old_refresh!
    replay_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert replay_resp.status_code == 401
    assert "reuse detected" in replay_resp.json()["error"]["message"]

    # 4. As a result of replay detection, the new_refresh MUST now be invalidated too!
    compromised_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh},
    )
    assert compromised_resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_single_session(client: httpx.AsyncClient):
    """Verify /auth/logout invalidates the specific refresh token."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout_user@example.com",
            "password": "LogoutSecure123!",
            "display_name": "Logout Tester",
        },
    )
    refresh_token = reg_resp.json()["data"]["tokens"]["refresh_token"]

    # Logout
    logout_resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 200

    # Attempting to refresh should fail
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_all_sessions(client: httpx.AsyncClient):
    """Verify /auth/logout-all revokes all sessions for the authenticated user."""
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout_all_user@example.com",
            "password": "LogoutAllSecure123!",
            "display_name": "Logout All Tester",
        },
    )
    r1 = reg_resp.json()["data"]["tokens"]["refresh_token"]

    # Login second device
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout_all_user@example.com", "password": "LogoutAllSecure123!"},
    )
    access_token = login_resp.json()["data"]["tokens"]["access_token"]
    r2 = login_resp.json()["data"]["tokens"]["refresh_token"]

    # Call logout-all
    logout_all_resp = await client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_all_resp.status_code == 200
    assert logout_all_resp.json()["data"]["sessions_revoked"] >= 2

    # Both refresh tokens must now be revoked
    for tok in [r1, r2]:
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": tok})
        assert resp.status_code == 401
