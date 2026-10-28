"""Tests for Phase 10: Routines, Reminders, and Product Reactions.

Covers:
- Routine creation, strict step ordering, and duplicate step_order rejection
- Completion history persistence separated from mutable routine definitions
- Timezone-aware completion dates/times using user's configured IANA timezone
- Reminder preferences, opt-outs, quiet hours, idempotent duplicate prevention,
  and delivery failure handling
- Clear distinction of the local recording notification adapter (`is_simulated=True`,
  `actual_external_delivery=False`) from actual external delivery
- Product reaction persistence, non-diagnostic framing, and urgent-care guidance
  escalation when severe or rapidly worsening reactions are reported
- Strict cross-user access denial across routines, completions, shelf items, and reactions
"""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product
from app.providers.notification import (
    LocalRecordingNotificationAdapter,
    get_notification_provider,
)


async def _register_and_login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "display_name": email.split("@")[0],
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["data"]["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_catalogue_product(session: AsyncSession) -> Product:
    product = Product(
        name="ToneTrace Gentle Barrier Cleanser",
        brand="ToneTrace Lab",
        category="cleanser",
        description="Gentle barrier-supporting cleanser.",
        full_ingredient_list="Aqua, Glycerin, Panthenol",
        ean_or_upc="0099112233499",
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


@pytest.mark.asyncio
async def test_routine_creation_step_ordering_and_edit_preserves_completion_history(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
):
    """Verify routine creation, step ordering, and that editing steps preserves history."""
    catalogue_product = await _seed_catalogue_product(test_session)
    headers = await _register_and_login(client, "routine_owner@example.com")

    # Add a custom product to the user's shelf
    shelf_resp = await client.post(
        "/api/v1/me/shelf",
        headers=headers,
        json={
            "custom_name": "Custom Azelaic Acid 10% Cream",
            "custom_brand": "DermCustom",
            "custom_category": "treatment",
            "status": "in_use",
        },
    )
    assert shelf_resp.status_code == 201, shelf_resp.text
    shelf_item_id = shelf_resp.json()["data"]["id"]

    # 1. Duplicate step_order values are rejected with 422
    dup_resp = await client.post(
        "/api/v1/me/routines",
        headers=headers,
        json={
            "name": "Invalid Duplicate Order Routine",
            "time_of_day": "morning",
            "steps": [
                {"step_order": 1, "product_id": str(catalogue_product.id)},
                {"step_order": 1, "user_product_id": shelf_item_id},
            ],
        },
    )
    assert dup_resp.status_code == 422
    assert dup_resp.json()["error"]["code"] == "DUPLICATE_ROUTINE_STEP_ORDER"

    # 2. Submit steps out of order (3, 1, 2) and verify deterministic ordering (1, 2, 3)
    create_resp = await client.post(
        "/api/v1/me/routines",
        headers=headers,
        json={
            "name": "Morning Brightening Routine",
            "description": "Gentle cleanse, custom treatment, and wait step",
            "time_of_day": "morning",
            "frequency": "daily",
            "preferred_local_time": "08:00",
            "steps": [
                {
                    "step_order": 3,
                    "custom_instruction": "Apply broad-spectrum SPF 50 generously",
                    "frequency": "daily",
                },
                {
                    "step_order": 1,
                    "product_id": str(catalogue_product.id),
                    "custom_instruction": "Massage onto damp skin for 30 seconds",
                },
                {
                    "step_order": 2,
                    "user_product_id": shelf_item_id,
                    "wait_time_seconds": 300,
                },
            ],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    routine = create_resp.json()["data"]
    routine_id = routine["id"]
    assert routine["version"] == 1
    assert [s["step_order"] for s in routine["steps"]] == [1, 2, 3]
    assert routine["steps"][0]["step_label"] == "ToneTrace Gentle Barrier Cleanser"
    assert routine["steps"][1]["step_label"] == "Custom Azelaic Acid 10% Cream"
    assert routine["steps"][2]["step_label"] == "Apply broad-spectrum SPF 50 generously"

    # 3. Record a completion against version 1 of the routine
    comp_resp = await client.post(
        f"/api/v1/me/routines/{routine_id}/completions",
        headers=headers,
        json={
            "status": "completed",
            "notes": "Completed all 3 morning steps before work.",
        },
    )
    assert comp_resp.status_code == 201, comp_resp.text
    comp_data = comp_resp.json()["data"]
    assert comp_data["routine_version_snapshot"] == 1
    assert comp_data["routine_name_snapshot"] == "Morning Brightening Routine"
    assert len(comp_data["completed_steps_snapshot"]) == 3

    # 4. Edit the routine (rename + replace with 1 step) and confirm completion history is intact
    patch_resp = await client.patch(
        f"/api/v1/me/routines/{routine_id}",
        headers=headers,
        json={
            "name": "Minimalist Morning Routine v2",
            "steps": [
                {
                    "step_order": 1,
                    "product_id": str(catalogue_product.id),
                }
            ],
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    updated_routine = patch_resp.json()["data"]
    assert updated_routine["version"] == 2
    assert updated_routine["name"] == "Minimalist Morning Routine v2"
    assert len(updated_routine["steps"]) == 1
    assert updated_routine["total_completions"] == 1

    # Historical completion still preserves the v1 name, v1 version, and all 3 original steps
    hist_resp = await client.get(
        f"/api/v1/me/routines/{routine_id}/completions",
        headers=headers,
    )
    assert hist_resp.status_code == 200
    hist_items = hist_resp.json()["data"]["items"]
    assert len(hist_items) == 1
    assert hist_items[0]["routine_version_snapshot"] == 1
    assert hist_items[0]["routine_name_snapshot"] == "Morning Brightening Routine"
    assert len(hist_items[0]["completed_steps_snapshot"]) == 3


@pytest.mark.asyncio
async def test_routine_completion_timezone_behavior_and_idempotency(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
):
    """Verify completion timestamps respect the user's configured IANA timezone and idempotency."""
    catalogue_product = await _seed_catalogue_product(test_session)
    headers = await _register_and_login(client, "tz_user@example.com")

    # Configure user timezone to Asia/Tokyo (UTC+9) via PUT /api/v1/me/reminders
    rem_resp = await client.put(
        "/api/v1/me/reminders",
        headers=headers,
        json={
            "reminders_enabled": True,
            "preferred_channels": ["in_app"],
            "morning_reminder_enabled": True,
            "morning_reminder_time": "08:00",
            "evening_reminder_enabled": True,
            "evening_reminder_time": "21:00",
            "quiet_hours_enabled": True,
            "quiet_hours_start": "22:30",
            "quiet_hours_end": "07:00",
            "timezone_override": "Asia/Tokyo",
        },
    )
    assert rem_resp.status_code == 200, rem_resp.text
    assert rem_resp.json()["data"]["effective_timezone"] == "Asia/Tokyo"

    routine_resp = await client.post(
        "/api/v1/me/routines",
        headers=headers,
        json={
            "name": "Tokyo Morning Routine",
            "time_of_day": "morning",
            "steps": [{"step_order": 1, "product_id": str(catalogue_product.id)}],
        },
    )
    routine_id = routine_resp.json()["data"]["id"]

    # 2026-10-27T20:30:00Z in UTC is 2026-10-28 05:30:00 in Asia/Tokyo (next calendar day!)
    comp_1 = await client.post(
        f"/api/v1/me/routines/{routine_id}/completions",
        headers=headers,
        json={
            "status": "completed",
            "completed_at": "2026-10-27T20:30:00Z",
            "idempotency_key": "tokyo-comp-2026-10-28",
        },
    )
    assert comp_1.status_code == 201, comp_1.text
    c1_data = comp_1.json()["data"]
    assert c1_data["user_timezone"] == "Asia/Tokyo"
    assert c1_data["local_date"] == "2026-10-28"
    assert c1_data["local_time"] == "05:30:00"

    # Re-submitting with the same idempotency_key returns the same record without duplication
    comp_2 = await client.post(
        f"/api/v1/me/routines/{routine_id}/completions",
        headers=headers,
        json={
            "status": "completed",
            "completed_at": "2026-10-27T20:30:00Z",
            "idempotency_key": "tokyo-comp-2026-10-28",
        },
    )
    assert comp_2.status_code == 201
    assert comp_2.json()["data"]["id"] == c1_data["id"]

    list_resp = await client.get(f"/api/v1/me/routines/{routine_id}/completions", headers=headers)
    assert list_resp.json()["data"]["total"] == 1


@pytest.mark.asyncio
async def test_reminders_local_adapter_distinction_quiet_hours_opt_out_and_deduplication(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
    app,
):
    """Verify local notification adapter disclosure, quiet hours, opt-outs, and deduplication."""
    catalogue_product = await _seed_catalogue_product(test_session)
    local_adapter = LocalRecordingNotificationAdapter()
    app.dependency_overrides[get_notification_provider] = lambda: local_adapter

    try:
        headers = await _register_and_login(client, "reminder_tester@example.com")

        # Configure America/New_York (EDT = UTC-4 in October) with quiet hours 22:30 - 07:00
        put_resp = await client.put(
            "/api/v1/me/reminders",
            headers=headers,
            json={
                "reminders_enabled": True,
                "preferred_channels": ["in_app"],
                "morning_reminder_enabled": True,
                "morning_reminder_time": "08:00",
                "evening_reminder_enabled": True,
                "evening_reminder_time": "21:00",
                "quiet_hours_enabled": True,
                "quiet_hours_start": "22:30",
                "quiet_hours_end": "07:00",
                "timezone_override": "America/New_York",
            },
        )
        assert put_resp.status_code == 200
        prefs = put_resp.json()["data"]
        assert prefs["is_simulated_delivery"] is True
        assert prefs["active_notification_provider"] == "local_test_recorder"

        routine_resp = await client.post(
            "/api/v1/me/routines",
            headers=headers,
            json={
                "name": "NY Morning Routine",
                "time_of_day": "morning",
                "steps": [{"step_order": 1, "product_id": str(catalogue_product.id)}],
            },
        )
        routine_id = routine_resp.json()["data"]["id"]

        # 1. Dispatch at 12:30 UTC (08:30 EDT -> outside quiet hours)
        disp_1 = await client.post(
            "/api/v1/me/reminders/dispatch",
            headers=headers,
            json={
                "routine_id": routine_id,
                "slot": "morning",
                "channel": "in_app",
                "scheduled_for_utc": datetime(2026, 10, 27, 12, 30, tzinfo=UTC).isoformat(),
                "idempotency_key": "ny-morning-2026-10-27",
            },
        )
        assert disp_1.status_code == 200, disp_1.text
        d1 = disp_1.json()["data"]
        assert d1["status"] == "recorded_local_not_sent"
        assert d1["provider"] == "local_test_recorder"
        assert d1["is_simulated"] is True
        assert d1["actual_external_delivery"] is False
        assert "SIMULATED LOCAL RECORDING ONLY" in d1["delivery_mode_disclosure"]
        assert d1["duplicate_prevented"] is False
        assert d1["user_timezone"] == "America/New_York"
        assert d1["user_local_time"] == "2026-10-27 08:30:00"
        assert len(local_adapter.recorded_messages) == 1

        # 2. Duplicate dispatch with the same idempotency_key is prevented
        disp_dup = await client.post(
            "/api/v1/me/reminders/dispatch",
            headers=headers,
            json={
                "routine_id": routine_id,
                "slot": "morning",
                "channel": "in_app",
                "scheduled_for_utc": datetime(2026, 10, 27, 12, 30, tzinfo=UTC).isoformat(),
                "idempotency_key": "ny-morning-2026-10-27",
            },
        )
        assert disp_dup.status_code == 200
        d_dup = disp_dup.json()["data"]
        assert d_dup["status"] == "suppressed_duplicate"
        assert d_dup["duplicate_prevented"] is True
        # Local adapter was NOT called a second time
        assert len(local_adapter.recorded_messages) == 1

        # 3. Dispatch during local quiet hours (03:30 UTC = 23:30 EDT on Oct 26)
        disp_quiet = await client.post(
            "/api/v1/me/reminders/dispatch",
            headers=headers,
            json={
                "routine_id": routine_id,
                "slot": "evening",
                "channel": "in_app",
                "scheduled_for_utc": datetime(2026, 10, 27, 3, 30, tzinfo=UTC).isoformat(),
                "idempotency_key": "ny-quiet-hour-test",
            },
        )
        assert disp_quiet.status_code == 200
        d_quiet = disp_quiet.json()["data"]
        assert d_quiet["status"] == "suppressed_quiet_hours"
        assert "quiet hours" in (d_quiet["failure_reason"] or "").lower()
        assert len(local_adapter.recorded_messages) == 1

        # 4. Opt out of reminders -> suppressed_opt_out
        opt_out_resp = await client.put(
            "/api/v1/me/reminders",
            headers=headers,
            json={
                "reminders_enabled": False,
                "preferred_channels": ["in_app"],
                "morning_reminder_enabled": True,
                "morning_reminder_time": "08:00",
                "evening_reminder_enabled": True,
                "evening_reminder_time": "21:00",
                "quiet_hours_enabled": True,
                "quiet_hours_start": "22:30",
                "quiet_hours_end": "07:00",
                "timezone_override": "America/New_York",
            },
        )
        assert opt_out_resp.status_code == 200
        assert opt_out_resp.json()["data"]["opted_out_at"] is not None

        disp_opt_out = await client.post(
            "/api/v1/me/reminders/dispatch",
            headers=headers,
            json={
                "routine_id": routine_id,
                "slot": "morning",
                "channel": "in_app",
                "scheduled_for_utc": datetime(2026, 10, 28, 12, 30, tzinfo=UTC).isoformat(),
                "idempotency_key": "ny-opted-out-test",
            },
        )
        assert disp_opt_out.status_code == 200
        assert disp_opt_out.json()["data"]["status"] == "suppressed_opt_out"
        assert len(local_adapter.recorded_messages) == 1

        # 5. Re-enable reminders and test graceful handling of provider delivery failure
        await client.put(
            "/api/v1/me/reminders",
            headers=headers,
            json={
                "reminders_enabled": True,
                "preferred_channels": ["in_app"],
                "morning_reminder_enabled": True,
                "morning_reminder_time": "08:00",
                "evening_reminder_enabled": True,
                "evening_reminder_time": "21:00",
                "quiet_hours_enabled": True,
                "quiet_hours_start": "22:30",
                "quiet_hours_end": "07:00",
                "timezone_override": "America/New_York",
            },
        )
        local_adapter.set_simulated_failure("Simulated notification bus outage")
        disp_fail = await client.post(
            "/api/v1/me/reminders/dispatch",
            headers=headers,
            json={
                "routine_id": routine_id,
                "slot": "morning",
                "channel": "in_app",
                "scheduled_for_utc": datetime(2026, 10, 29, 12, 30, tzinfo=UTC).isoformat(),
                "idempotency_key": "ny-failure-test",
            },
        )
        assert disp_fail.status_code == 200
        d_fail = disp_fail.json()["data"]
        assert d_fail["status"] == "failed"
        assert d_fail["failure_reason"] == "Simulated notification bus outage"
    finally:
        app.dependency_overrides.pop(get_notification_provider, None)


@pytest.mark.asyncio
async def test_product_reactions_persistence_non_diagnostic_framing_and_urgent_care_escalation(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
):
    """Verify reaction persistence, non-diagnostic framing, and urgent-care guidance escalation."""
    catalogue_product = await _seed_catalogue_product(test_session)
    headers = await _register_and_login(client, "reaction_user@example.com")

    # 1. Mild reaction -> persisted as observation only, no urgent care escalation
    mild_resp = await client.post(
        "/api/v1/me/product-reactions",
        headers=headers,
        json={
            "product_id": str(catalogue_product.id),
            "reaction_type": "dryness",
            "severity": "mild",
            "symptoms": ["slight tightness"],
            "is_rapidly_worsening": False,
            "suspected_ingredient_names": ["Cocamidopropyl Betaine"],
            "notes": "Slight tightness around chin after washing.",
        },
    )
    assert mild_resp.status_code == 201, mild_resp.text
    mild_data = mild_resp.json()["data"]
    assert mild_data["is_causal_proof"] is False
    assert mild_data["is_medical_diagnosis"] is False
    assert mild_data["requires_urgent_care_guidance"] is False
    assert mild_data["urgent_care_guidance"] is None
    assert mild_data["ordinary_recommendations_suspended"] is False
    assert (
        "not prove that a product or ingredient caused a symptom"
        in (mild_data["epistemic_disclaimer"])
    )

    # 2. Severe / rapidly worsening reaction -> urgent-care guidance surfaced,
    #    ordinary recommendations suspended, never claims a clinical allergy diagnosis
    severe_resp = await client.post(
        "/api/v1/me/product-reactions",
        headers=headers,
        json={
            "product_id": str(catalogue_product.id),
            "reaction_type": "allergic_suspect",
            "severity": "severe",
            "symptoms": ["facial swelling", "widespread hives"],
            "is_rapidly_worsening": True,
            "notes": "Rapidly worsening redness and lip swelling within 15 minutes.",
        },
    )
    assert severe_resp.status_code == 201, severe_resp.text
    sev_data = severe_resp.json()["data"]
    assert sev_data["is_causal_proof"] is False
    assert sev_data["is_medical_diagnosis"] is False
    assert sev_data["requires_urgent_care_guidance"] is True
    assert sev_data["ordinary_recommendations_suspended"] is True
    assert sev_data["urgent_care_guidance"] is not None
    assert "URGENT CARE GUIDANCE" in sev_data["urgent_care_guidance"]
    assert "Stop using the suspected product(s) immediately" in sev_data["urgent_care_guidance"]

    # 3. List reactions and filter by severity
    list_all = await client.get("/api/v1/me/product-reactions", headers=headers)
    assert list_all.status_code == 200
    assert list_all.json()["data"]["total"] == 2

    list_severe = await client.get(
        "/api/v1/me/product-reactions?severity=severe",
        headers=headers,
    )
    assert list_severe.status_code == 200
    sev_items = list_severe.json()["data"]["items"]
    assert len(sev_items) == 1
    assert sev_items[0]["id"] == sev_data["id"]


@pytest.mark.asyncio
async def test_cross_user_access_denial_for_routines_shelf_references_and_reactions(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
):
    """Verify strict ownership isolation across routines, shelf references, and reactions."""
    catalogue_product = await _seed_catalogue_product(test_session)
    headers_a = await _register_and_login(client, "user_a_routine@example.com")
    headers_b = await _register_and_login(client, "user_b_intruder@example.com")

    # User A creates a shelf item, a routine, and a reaction
    shelf_a = await client.post(
        "/api/v1/me/shelf",
        headers=headers_a,
        json={"product_id": str(catalogue_product.id), "status": "in_use"},
    )
    shelf_a_id = shelf_a.json()["data"]["id"]

    routine_a = await client.post(
        "/api/v1/me/routines",
        headers=headers_a,
        json={
            "name": "User A Private Evening Routine",
            "time_of_day": "evening",
            "steps": [{"step_order": 1, "user_product_id": shelf_a_id}],
        },
    )
    routine_a_id = routine_a.json()["data"]["id"]

    await client.post(
        "/api/v1/me/product-reactions",
        headers=headers_a,
        json={
            "user_product_id": shelf_a_id,
            "routine_id": routine_a_id,
            "reaction_type": "stinging",
            "severity": "mild",
        },
    )

    # User B cannot read, patch, delete, or complete User A's routine
    assert (
        await client.get(f"/api/v1/me/routines/{routine_a_id}", headers=headers_b)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/me/routines/{routine_a_id}",
            headers=headers_b,
            json={"name": "Hijacked Routine"},
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/me/routines/{routine_a_id}", headers=headers_b)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/me/routines/{routine_a_id}/completions",
            headers=headers_b,
            json={"status": "completed"},
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/me/routines/{routine_a_id}/completions", headers=headers_b)
    ).status_code == 404

    # User B cannot create a routine step referencing User A's shelf item
    cross_shelf_routine = await client.post(
        "/api/v1/me/routines",
        headers=headers_b,
        json={
            "name": "User B Routine Referencing User A Shelf",
            "time_of_day": "morning",
            "steps": [{"step_order": 1, "user_product_id": shelf_a_id}],
        },
    )
    assert cross_shelf_routine.status_code == 404
    assert cross_shelf_routine.json()["error"]["code"] == "SHELF_ITEM_NOT_FOUND"

    # User B cannot log a reaction referencing User A's shelf item or routine
    cross_reaction = await client.post(
        "/api/v1/me/product-reactions",
        headers=headers_b,
        json={
            "user_product_id": shelf_a_id,
            "reaction_type": "redness",
            "severity": "mild",
        },
    )
    assert cross_reaction.status_code == 404

    # User B sees 0 routines and 0 reactions on their own endpoints
    b_routines = await client.get("/api/v1/me/routines", headers=headers_b)
    assert b_routines.json()["data"]["total"] == 0
    b_reactions = await client.get("/api/v1/me/product-reactions", headers=headers_b)
    assert b_reactions.json()["data"]["total"] == 0
