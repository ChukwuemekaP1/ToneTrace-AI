"""Integration tests for user profiles and skin attributes.

Tests sensitivities and strict cross-user data isolation.
"""

import httpx
import pytest

from app.core.security import auth_rate_limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Ensure in-memory rate limiter is reset before each test."""
    auth_rate_limiter.reset()


async def register_and_get_token(client: httpx.AsyncClient, email: str) -> str:
    """Helper fixture to create a user and return their access token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "ValidPassword123!",
            "display_name": f"User {email.split('@')[0]}",
        },
    )
    return resp.json()["data"]["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_get_me_aggregate_profile(client: httpx.AsyncClient):
    """Verify /me returns user metadata, profile, blank skin profile, and empty sensitivities."""
    token = await register_and_get_token(client, "me_tester@example.com")

    response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["user"]["email"] == "me_tester@example.com"
    assert data["profile"]["display_name"] == "User me_tester"
    assert data["profile"]["timezone"] == "UTC"
    assert data["skin_profile"] is not None
    assert data["skin_profile"]["skin_type"] is None
    assert data["sensitivities"] == []


@pytest.mark.asyncio
async def test_update_user_profile(client: httpx.AsyncClient):
    """Verify PATCH /me updates display name and timezone."""
    token = await register_and_get_token(client, "patch_profile@example.com")

    patch_payload = {
        "display_name": "Radiant Skin Enthusiast",
        "timezone": "America/New_York",
    }
    response = await client.patch(
        "/api/v1/me",
        json=patch_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["display_name"] == "Radiant Skin Enthusiast"
    assert data["timezone"] == "America/New_York"


@pytest.mark.asyncio
async def test_skin_profile_update(client: httpx.AsyncClient):
    """Verify PUT /me/skin-profile updates skin type, concerns, and skincare goals."""
    token = await register_and_get_token(client, "skin_tester@example.com")

    update_payload = {
        "skin_type": "combination",
        "skin_concerns": ["hyperpigmentation", "redness", "breakouts"],
        "skin_goals": ["barrier_support", "brightening"],
    }
    response = await client.put(
        "/api/v1/me/skin-profile",
        json=update_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["skin_type"] == "combination"
    assert "hyperpigmentation" in data["skin_concerns"]
    assert "brightening" in data["skin_goals"]


@pytest.mark.asyncio
async def test_sensitivities_crud_and_conflict_handling(client: httpx.AsyncClient):
    """Verify adding, listing, conflict detection, and deleting user ingredient sensitivities."""
    token = await register_and_get_token(client, "sensitivity_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Add sensitivity
    add_resp = await client.post(
        "/api/v1/me/sensitivities",
        json={
            "ingredient_name": "Niacinamide",
            "severity": "high",
            "notes": "Causes immediate flushing and redness",
        },
        headers=headers,
    )
    assert add_resp.status_code == 201
    sens_id = add_resp.json()["data"]["id"]
    assert add_resp.json()["data"]["ingredient_name"] == "niacinamide"

    # 2. Duplicate sensitivity conflict
    dup_resp = await client.post(
        "/api/v1/me/sensitivities",
        json={"ingredient_name": "NIACINAMIDE", "severity": "moderate"},
        headers=headers,
    )
    assert dup_resp.status_code == 409

    # 3. List sensitivities
    list_resp = await client.get("/api/v1/me/sensitivities", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 1

    # 4. Delete sensitivity
    del_resp = await client.delete(f"/api/v1/me/sensitivities/{sens_id}", headers=headers)
    assert del_resp.status_code == 200

    # 5. List is now empty
    empty_resp = await client.get("/api/v1/me/sensitivities", headers=headers)
    assert empty_resp.json()["data"] == []


@pytest.mark.asyncio
async def test_cross_user_isolation(client: httpx.AsyncClient):
    """Zero-Trust Boundary: User A cannot delete or access User B's resources."""
    token_a = await register_and_get_token(client, "user_a@example.com")
    token_b = await register_and_get_token(client, "user_b@example.com")

    # User A adds a sensitivity
    res_a = await client.post(
        "/api/v1/me/sensitivities",
        json={"ingredient_name": "Fragrance", "severity": "severe"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    sens_id_a = res_a.json()["data"]["id"]

    # User B attempts to DELETE User A's sensitivity
    hack_del_resp = await client.delete(
        f"/api/v1/me/sensitivities/{sens_id_a}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert hack_del_resp.status_code == 404
    assert "not found or access denied" in hack_del_resp.json()["error"]["message"]

    # User B's sensitivities list should remain empty
    b_sens = await client.get(
        "/api/v1/me/sensitivities",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert b_sens.json()["data"] == []
