"""Tests for Phase 8: Skin Analysis and Longitudinal Skin Story.

NOTE: All tests in this suite use deterministic mock adapters (`MockSkinAnalysisAdapter`)
or simulated HTTP transports (`httpx.MockTransport`). None of these unit/integration tests
make live network calls to Perfect Corp / YouCam servers, and mock-based tests are
explicitly distinguished from live provider integration tests.
"""

import io

import httpx
import pytest
from PIL import Image

from app.providers.skin_analysis import (
    MockSkinAnalysisAdapter,
    SkinAnalysisRateLimitError,
    YouCamSkinAnalysisAdapter,
    get_skin_analysis_provider,
)


def _make_test_image_bytes(
    color: tuple[int, int, int] = (210, 170, 150),
    size: tuple[int, int] = (128, 128),
    fmt: str = "JPEG",
) -> bytes:
    """Create a valid in-memory test image with deterministic RGB pixel content."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=fmt)
    return buf.getvalue()


async def _register_and_login(
    client: httpx.AsyncClient,
    email: str,
) -> dict[str, str]:
    """Register a user and return Authorization Bearer headers."""
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


async def _set_skin_consent(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    is_granted: bool = True,
) -> None:
    """Grant or revoke 'skin_data_processing' consent for the authenticated user."""
    resp = await client.put(
        "/api/v1/me/consents/skin_data_processing",
        headers=headers,
        json={
            "policy_version": "1.0.0",
            "is_granted": is_granted,
        },
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_skin_scan_requires_explicit_consent(client: httpx.AsyncClient, app):
    """Verify scan submission is rejected (403) when consent is missing or revoked."""
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter()
    try:
        headers = await _register_and_login(client, "consent_check@example.com")
        img_bytes = _make_test_image_bytes()

        # 1. No consent granted yet -> 403 PermissionDeniedError
        res_no_consent = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("selfie.jpg", img_bytes, "image/jpeg")},
        )
        assert res_no_consent.status_code == 403
        assert res_no_consent.json()["error"]["code"] == "PERMISSION_DENIED"

        # 2. Grant consent -> 201 Created
        await _set_skin_consent(client, headers, is_granted=True)
        res_granted = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("selfie.jpg", img_bytes, "image/jpeg")},
        )
        assert res_granted.status_code == 201

        # 3. Revoke consent -> subsequent scan rejected with 403
        await _set_skin_consent(client, headers, is_granted=False)
        res_revoked = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("selfie2.jpg", img_bytes, "image/jpeg")},
        )
        assert res_revoked.status_code == 403
    finally:
        app.dependency_overrides.pop(get_skin_analysis_provider, None)


@pytest.mark.asyncio
async def test_skin_scan_creation_and_observation_normalization_mock(
    client: httpx.AsyncClient,
    app,
):
    """Deterministic mock-adapter test verifying scan creation, private media, and normalization."""
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter(
        model_version="mock-deterministic-v1.0"
    )
    try:
        headers = await _register_and_login(client, "scan_create@example.com")
        await _set_skin_consent(client, headers, is_granted=True)

        img_bytes = _make_test_image_bytes(color=(200, 160, 140))
        resp = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("morning_scan.jpg", img_bytes, "image/jpeg")},
            data={
                "lighting_condition": "natural_daylight",
                "camera_angle": "frontal",
                "cosmetics_worn": "false",
                "capture_notes": "Taken near window in morning daylight",
                "requested_metrics": "spots,redness,texture,pores",
            },
        )
        assert resp.status_code == 201, resp.text
        scan = resp.json()["data"]
        assert scan["status"] == "succeeded"
        assert scan["provider"] == "mock"
        assert scan["provider_model_version"] == "mock-deterministic-v1.0"
        assert scan["raw_payload_retained"] is False
        assert scan["capture_conditions"]["lighting_condition"] == "natural_daylight"
        assert scan["capture_conditions"]["cosmetics_worn"] is False
        assert len(scan["observations"]) == 4

        metric_codes = {o["metric_code"] for o in scan["observations"]}
        assert metric_codes == {"spots", "redness", "texture", "pores"}
        for obs in scan["observations"]:
            assert obs["unit"] == "score_0_100"
            assert obs["provider_name"] == "mock"
            assert obs["provider_model_version"] == "mock-deterministic-v1.0"
            assert obs["interpretation_version"] == "tonetrace-obs-v1.0"
            assert "lighting" in obs["caveat_note"].lower()

        assert len(scan["media_items"]) == 1
        media = scan["media_items"][0]
        assert media["is_deleted"] is False
        assert media["signed_view_url"] is not None
    finally:
        app.dependency_overrides.pop(get_skin_analysis_provider, None)


@pytest.mark.asyncio
async def test_skin_scan_provider_timeout_and_unavailable_never_fabricates_success(
    client: httpx.AsyncClient,
    app,
):
    """Verify provider timeouts and 503 unavailability never fabricate scan success."""
    headers = await _register_and_login(client, "timeout_user@example.com")
    await _set_skin_consent(client, headers, is_granted=True)
    img_bytes = _make_test_image_bytes()

    # 1. Provider timeout
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter(
        simulate_timeout=True
    )
    try:
        resp_timeout = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("timeout.jpg", img_bytes, "image/jpeg")},
        )
        assert resp_timeout.status_code == 201
        scan_timeout = resp_timeout.json()["data"]
        assert scan_timeout["status"] == "failed"
        assert scan_timeout["error_category"] == "provider_timeout"
        assert scan_timeout["observations"] == []
        assert scan_timeout["overall_score"] is None
    finally:
        app.dependency_overrides.pop(get_skin_analysis_provider, None)

    # 2. Provider unavailable
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter(
        simulate_unavailable=True
    )
    try:
        resp_unavail = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("unavail.jpg", img_bytes, "image/jpeg")},
        )
        assert resp_unavail.status_code == 201
        scan_unavail = resp_unavail.json()["data"]
        assert scan_unavail["status"] == "failed"
        assert scan_unavail["error_category"] == "provider_unavailable"
        assert scan_unavail["observations"] == []
    finally:
        app.dependency_overrides.pop(get_skin_analysis_provider, None)


@pytest.mark.asyncio
async def test_skin_scan_asynchronous_processing_to_succeeded_transition(
    client: httpx.AsyncClient,
    app,
):
    """Verify async scan lifecycle ('processing' -> poll -> 'succeeded') with mock adapter."""
    async_adapter = MockSkinAnalysisAdapter(simulate_async=True)
    app.dependency_overrides[get_skin_analysis_provider] = lambda: async_adapter
    try:
        headers = await _register_and_login(client, "async_poll@example.com")
        await _set_skin_consent(client, headers, is_granted=True)
        img_bytes = _make_test_image_bytes(color=(190, 150, 130))

        create_resp = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("async_face.jpg", img_bytes, "image/jpeg")},
            data={"requested_metrics": "spots,redness"},
        )
        assert create_resp.status_code == 201
        initial_scan = create_resp.json()["data"]
        scan_id = initial_scan["id"]
        assert initial_scan["status"] == "processing"
        assert initial_scan["provider_task_id"] is not None
        assert initial_scan["observations"] == []

        # Poll the scan to transition to succeeded
        poll_resp = await client.post(
            f"/api/v1/skin/scans/{scan_id}/poll",
            headers=headers,
        )
        assert poll_resp.status_code == 200
        completed_scan = poll_resp.json()["data"]
        assert completed_scan["status"] == "succeeded"
        assert len(completed_scan["observations"]) == 2
        assert {o["metric_code"] for o in completed_scan["observations"]} == {"spots", "redness"}
    finally:
        app.dependency_overrides.pop(get_skin_analysis_provider, None)


@pytest.mark.asyncio
async def test_skin_scan_idempotency_and_failed_scan_retry_recovery(
    client: httpx.AsyncClient,
    app,
):
    """Verify idempotency_key deduplication and in-place retry recovery of failed scans."""
    headers = await _register_and_login(client, "idempotent_user@example.com")
    await _set_skin_consent(client, headers, is_granted=True)
    img_bytes = _make_test_image_bytes(color=(215, 175, 155))

    # Part A: First attempt with 'retry-key-001' times out -> status='failed'
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter(
        simulate_timeout=True
    )
    resp_fail = await client.post(
        "/api/v1/skin/scans",
        headers=headers,
        files={"file": ("retry.jpg", img_bytes, "image/jpeg")},
        data={"idempotency_key": "retry-key-001"},
    )
    assert resp_fail.status_code == 201
    failed_scan_id = resp_fail.json()["data"]["id"]
    assert resp_fail.json()["data"]["status"] == "failed"

    # Part B: Retry with same 'retry-key-001' when provider is healthy -> recovers SAME scan ID!
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter()
    try:
        resp_recovered = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("retry.jpg", img_bytes, "image/jpeg")},
            data={"idempotency_key": "retry-key-001"},
        )
        assert resp_recovered.status_code == 201
        recovered_data = resp_recovered.json()["data"]
        assert recovered_data["id"] == failed_scan_id
        assert recovered_data["status"] == "succeeded"
        assert len(recovered_data["observations"]) > 0

        # Part C: Sending a third request with 'retry-key-001' returns the existing succeeded scan
        resp_dup = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("retry.jpg", img_bytes, "image/jpeg")},
            data={"idempotency_key": "retry-key-001"},
        )
        assert resp_dup.status_code == 201
        assert resp_dup.json()["data"]["id"] == failed_scan_id

        # Confirm total scans for user is still 1 (no duplicate scan records)
        list_resp = await client.get("/api/v1/skin/scans", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["data"]["total"] == 1
    finally:
        app.dependency_overrides.pop(get_skin_analysis_provider, None)


@pytest.mark.asyncio
async def test_skin_scan_cross_user_isolation_private_media_and_deletion(
    client: httpx.AsyncClient,
    app,
):
    """Verify ownership checks, private signed URL viewing, and complete scan deletion."""
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter()
    try:
        headers_a = await _register_and_login(client, "user_a_skin@example.com")
        headers_b = await _register_and_login(client, "user_b_skin@example.com")
        await _set_skin_consent(client, headers_a, is_granted=True)
        await _set_skin_consent(client, headers_b, is_granted=True)

        img_bytes = _make_test_image_bytes(color=(180, 140, 120))
        create_resp = await client.post(
            "/api/v1/skin/scans",
            headers=headers_a,
            files={"file": ("user_a.jpg", img_bytes, "image/jpeg")},
        )
        assert create_resp.status_code == 201
        scan_data = create_resp.json()["data"]
        scan_id = scan_data["id"]
        signed_url = scan_data["media_items"][0]["signed_view_url"]
        assert signed_url is not None

        # 1. Signed URL streams private image bytes
        view_ok = await client.get(signed_url)
        assert view_ok.status_code == 200
        assert view_ok.content == img_bytes

        # 2. Tampered signature is rejected with 403
        view_tampered = await client.get(f"{signed_url}tampered")
        assert view_tampered.status_code == 403

        # 3. User B cannot view, poll, delete, or link User A's scan
        assert (
            await client.get(f"/api/v1/skin/scans/{scan_id}", headers=headers_b)
        ).status_code == 404
        assert (
            await client.post(f"/api/v1/skin/scans/{scan_id}/poll", headers=headers_b)
        ).status_code == 404
        assert (
            await client.delete(f"/api/v1/skin/scans/{scan_id}", headers=headers_b)
        ).status_code == 404
        journal_cross_link = await client.post(
            "/api/v1/skin/journal",
            headers=headers_b,
            json={
                "skin_scan_id": scan_id,
                "perceived_skin_state": "calm",
            },
        )
        assert journal_cross_link.status_code == 404

        # 4. User A deletes their scan -> private storage object is purged and scan becomes 404
        del_resp = await client.delete(f"/api/v1/skin/scans/{scan_id}", headers=headers_a)
        assert del_resp.status_code == 200
        del_data = del_resp.json()["data"]
        assert del_data["status"] == "deleted"
        assert del_data["purged_media_count"] == 1

        # Previously valid signed URL now returns 404 because underlying object was deleted
        view_after_delete = await client.get(signed_url)
        assert view_after_delete.status_code == 404

        # Deleted scan no longer appears in GET /scans/{scan_id} or GET /scans
        assert (
            await client.get(f"/api/v1/skin/scans/{scan_id}", headers=headers_a)
        ).status_code == 404
        list_after = await client.get("/api/v1/skin/scans", headers=headers_a)
        assert list_after.json()["data"]["total"] == 0
    finally:
        app.dependency_overrides.pop(get_skin_analysis_provider, None)


@pytest.mark.asyncio
async def test_longitudinal_skin_story_compatibility_and_journal_integration(
    client: httpx.AsyncClient,
    app,
):
    """Verify Skin Story compares compatible observations and flags incompatible versions."""
    headers = await _register_and_login(client, "story_user@example.com")
    await _set_skin_consent(client, headers, is_granted=True)

    # Scan 1 & Scan 2 with model version 'mock-deterministic-v1.0'
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter(
        model_version="mock-deterministic-v1.0"
    )
    img_1 = _make_test_image_bytes(color=(150, 120, 110))
    img_2 = _make_test_image_bytes(color=(220, 190, 175))

    r1 = await client.post(
        "/api/v1/skin/scans",
        headers=headers,
        files={"file": ("day1.jpg", img_1, "image/jpeg")},
        data={
            "lighting_condition": "natural_daylight",
            "requested_metrics": "spots,redness",
        },
    )
    assert r1.status_code == 201
    scan_1_id = r1.json()["data"]["id"]

    r2 = await client.post(
        "/api/v1/skin/scans",
        headers=headers,
        files={"file": ("day14.jpg", img_2, "image/jpeg")},
        data={
            "lighting_condition": "natural_daylight",
            "requested_metrics": "spots,redness",
        },
    )
    assert r2.status_code == 201

    # Scan 3 with upgraded/incompatible model version 'mock-deterministic-v2.0'
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter(
        model_version="mock-deterministic-v2.0"
    )
    try:
        img_3 = _make_test_image_bytes(color=(205, 180, 165))
        r3 = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("day28.jpg", img_3, "image/jpeg")},
            data={
                "lighting_condition": "indoor_warm",
                "requested_metrics": "spots,redness",
            },
        )
        assert r3.status_code == 201

        # Create a journal entry linked to Scan 1
        j_resp = await client.post(
            "/api/v1/skin/journal",
            headers=headers,
            json={
                "skin_scan_id": scan_1_id,
                "perceived_skin_state": "balanced",
                "self_reported_observations": ["mild redness after cleansing"],
                "routine_notes": "Used gentle cleanser and niacinamide serum",
                "products_used": ["Gentle Cleanser", "Niacinamide 5% Serum"],
                "environmental_or_lifestyle_factors": {"lighting": "morning daylight"},
            },
        )
        assert j_resp.status_code == 201

        # List journal entries
        j_list = await client.get("/api/v1/skin/journal", headers=headers)
        assert j_list.status_code == 200
        assert j_list.json()["data"]["total"] == 1

        # Fetch Skin Story
        story_resp = await client.get("/api/v1/skin/story", headers=headers)
        assert story_resp.status_code == 200
        story = story_resp.json()["data"]
        assert story["total_succeeded_scans"] == 3
        assert len(story["recent_journal_entries"]) == 1
        assert "lighting" in story["capture_variability_notice"].lower()
        assert "do not infer" in story["non_diagnostic_disclaimer"].lower()
        assert (
            "never infers the biological or medical cause of pigmentation"
            in (story["pigmentation_and_causation_guardrail"])
        )

        timelines = {t["metric_code"]: t for t in story["metric_timelines"]}
        assert set(timelines.keys()) == {"spots", "redness"}

        spots_tl = timelines["spots"]
        assert spots_tl["baseline_model_version"] == "mock-deterministic-v1.0"
        assert len(spots_tl["points"]) == 3
        assert spots_tl["comparable_point_count"] == 2
        assert spots_tl["points"][0]["is_comparable_to_baseline"] is True
        assert spots_tl["points"][1]["is_comparable_to_baseline"] is True
        assert spots_tl["points"][2]["is_comparable_to_baseline"] is False
        assert "model version" in spots_tl["points"][2]["incompatibility_reason"]
        assert len(spots_tl["compatibility_warnings"]) == 1

        # Delta is computed strictly from the 2 compatible points (point[1] - point[0])
        expected_delta = round(
            spots_tl["points"][1]["display_value"] - spots_tl["points"][0]["display_value"], 2
        )
        assert spots_tl["net_observed_delta"] == expected_delta
        assert spots_tl["observation_classification"] in (
            "visual_metric_increase",
            "visual_metric_decrease",
            "visual_metric_stable",
        )
        assert (
            "not be interpreted as verified clinical improvement"
            in (spots_tl["non_clinical_interpretation"])
        )
    finally:
        app.dependency_overrides.pop(get_skin_analysis_provider, None)


@pytest.mark.asyncio
async def test_youcam_s2s_v2_adapter_contract_with_simulated_transport():
    """Unit test for YouCamSkinAnalysisAdapter S2S v2.0 protocol using MockTransport."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/s2s/v2.0/file/skin-analysis":
            assert request.headers.get("Authorization") == "Bearer sk-test-youcam-key"
            return httpx.Response(
                200,
                json={
                    "status": 200,
                    "data": {
                        "files": [
                            {
                                "file_id": "file_abc_123",
                                "requests": [
                                    {
                                        "method": "PUT",
                                        "url": "https://mock-s3.makeupar.com/upload/file_abc_123",
                                        "headers": {
                                            "Content-Type": "image/jpeg",
                                            "Content-Length": "100",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                },
            )
        if request.method == "PUT" and request.url.host == "mock-s3.makeupar.com":
            return httpx.Response(200)
        if request.method == "POST" and path == "/s2s/v2.0/task/skin-analysis":
            return httpx.Response(
                200,
                json={"status": 200, "data": {"task_id": "task_xyz_789"}},
            )
        if request.method == "GET" and path == "/s2s/v2.0/task/skin-analysis/task_xyz_789":
            return httpx.Response(
                200,
                json={
                    "status": 200,
                    "data": {
                        "task_status": "success",
                        "results": {
                            "score_info": {
                                "age_spot": {"raw_score": 78.4, "ui_score": 78},
                                "redness": {"raw_score": 84.1, "ui_score": 84},
                                "texture": {"raw_score": 71.9, "ui_score": 72},
                                "pore": {"raw_score": 69.2, "ui_score": 69},
                                "all": {"score": 75.8},
                                "skin_type": {"skin_type": "combination"},
                            }
                        },
                    },
                },
            )
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = YouCamSkinAnalysisAdapter(
        api_key="sk-test-youcam-key",
        base_url="https://yce-api-01.makeupar.com",
        max_poll_attempts=2,
        poll_interval_seconds=0.0,
        http_client=mock_client,
    )
    result = await adapter.submit_scan(
        file_bytes=b"fake-jpeg-bytes",
        filename="face.jpg",
        content_type="image/jpeg",
        requested_metrics=["spots", "redness", "texture", "pores"],
    )
    assert result.status == "succeeded"
    assert result.provider_name == "youcam"
    assert result.provider_task_id == "task_xyz_789"
    assert result.overall_score == 75.8
    assert result.skin_type_observation == "combination"
    obs_by_code = {o.metric_code: o for o in result.observations}
    assert set(obs_by_code.keys()) == {"spots", "redness", "texture", "pores"}
    assert obs_by_code["spots"].raw_value == 78.4
    assert obs_by_code["spots"].display_value == 78.0

    # Verify rate-limit error mapping (429) raises SkinAnalysisRateLimitError
    def rate_limit_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"status": 429, "error": "exceed_max_Place_task_times"})

    rl_client = httpx.AsyncClient(transport=httpx.MockTransport(rate_limit_handler))
    rl_adapter = YouCamSkinAnalysisAdapter(
        api_key="sk-test-youcam-key",
        http_client=rl_client,
    )
    with pytest.raises(SkinAnalysisRateLimitError):
        await rl_adapter.submit_scan(
            file_bytes=b"fake-jpeg-bytes",
            filename="face.jpg",
            content_type="image/jpeg",
        )
    await mock_client.aclose()
    await rl_client.aclose()
