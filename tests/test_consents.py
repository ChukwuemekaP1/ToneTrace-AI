"""Integration tests for user consent lifecycle.

Tests purpose versioning, audit trails, and privacy isolation.
"""

import httpx
import pytest

from app.core.security import auth_rate_limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Ensure in-memory rate limiter is reset before each test."""
    auth_rate_limiter.reset()


async def register_and_get_token(client: httpx.AsyncClient, email: str) -> str:
    """Helper to create a user and return their access token."""
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
async def test_consent_grant_and_revoke_lifecycle(client: httpx.AsyncClient):
    """Verify granting and revoking consent records timestamps and audit metadata."""
    token = await register_and_get_token(client, "consent_user@example.com")
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "ToneTrace-iOS/1.0",
    }

    # 1. Grant consent for skin data processing
    grant_payload = {
        "policy_version": "1.0.0",
        "is_granted": True,
    }
    grant_resp = await client.put(
        "/api/v1/me/consents/skin_data_processing",
        json=grant_payload,
        headers=headers,
    )
    assert grant_resp.status_code == 200
    data = grant_resp.json()["data"]
    assert data["purpose"] == "skin_data_processing"
    assert data["policy_version"] == "1.0.0"
    assert data["is_granted"] is True
    assert data["granted_at"] is not None
    assert data["revoked_at"] is None
    assert data["audit_metadata"]["user_agent"] == "ToneTrace-iOS/1.0"

    # 2. Revoke consent
    revoke_payload = {
        "policy_version": "1.0.0",
        "is_granted": False,
    }
    revoke_resp = await client.put(
        "/api/v1/me/consents/skin_data_processing",
        json=revoke_payload,
        headers=headers,
    )
    assert revoke_resp.status_code == 200
    rev_data = revoke_resp.json()["data"]
    assert rev_data["is_granted"] is False
    assert rev_data["revoked_at"] is not None

    # 3. List consents
    list_resp = await client.get("/api/v1/me/consents", headers=headers)
    assert list_resp.status_code == 200
    consents = list_resp.json()["data"]
    assert len(consents) == 1
    assert consents[0]["purpose"] == "skin_data_processing"
    assert consents[0]["is_granted"] is False


@pytest.mark.asyncio
async def test_multiple_consent_purposes(client: httpx.AsyncClient):
    """Verify distinct purposes can be recorded and tracked separately."""
    token = await register_and_get_token(client, "multi_consent@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    purposes = ["terms_of_service", "privacy_policy", "marketing_updates"]
    for purpose in purposes:
        resp = await client.put(
            f"/api/v1/me/consents/{purpose}",
            json={"policy_version": "2026.1", "is_granted": True},
            headers=headers,
        )
        assert resp.status_code == 200

    list_resp = await client.get("/api/v1/me/consents", headers=headers)
    assert list_resp.status_code == 200
    recorded = {c["purpose"] for c in list_resp.json()["data"]}
    assert recorded == set(purposes)


@pytest.mark.asyncio
async def test_consent_cross_user_isolation(client: httpx.AsyncClient):
    """Verify user consent records are strictly isolated between accounts."""
    token_a = await register_and_get_token(client, "alice@example.com")
    token_b = await register_and_get_token(client, "bob@example.com")

    # Alice grants consent
    await client.put(
        "/api/v1/me/consents/facial_biometrics",
        json={"policy_version": "1.0", "is_granted": True},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Bob's consents list must be empty
    bob_resp = await client.get(
        "/api/v1/me/consents",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert bob_resp.status_code == 200
    assert bob_resp.json()["data"] == []
