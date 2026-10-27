"""Comprehensive tests for Phase 5: OCR and Product-Label Scanning.

Covers:
- Image validation (empty, corrupted, dimensions > 4096, unsupported formats).
- Local storage provider (safe traversal, HMAC tokens, retrieval, deletion).
- OCR adapters (Mock, Tesseract fallback, OCR.space contracts and rate-limits).
- API workflow:
  - Image upload and formulation segmentation.
  - Candidate review and confirmation.
  - Strict cross-user data isolation.
  - Signed URL asset streaming and token security.
  - Automatic catalog matching against canonical ingredients.
"""

import io
import time

import httpx
import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ingredient
from app.providers.ocr.base import (
    LocalOCRNotAvailableError,
    OCRExtractionError,
    OCRRateLimitError,
    OCRUnavailableError,
)
from app.providers.ocr.mock import MockOCRAdapter
from app.providers.ocr.ocr_space import OCRSpaceAdapter
from app.providers.ocr.tesseract import LocalTesseractOCRAdapter
from app.providers.storage.local import LocalStorageProvider


def create_test_image_bytes(
    format: str = "JPEG",
    size: tuple[int, int] = (100, 100),
    color: tuple[int, int, int] = (255, 0, 0),
) -> bytes:
    """Helper to generate valid in-memory image bytes."""
    buf = io.BytesIO()
    image = Image.new("RGB", size, color=color)
    image.save(buf, format=format)
    return buf.getvalue()


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


# ==============================================================================
# 1. STORAGE PROVIDER UNIT TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_local_storage_lifecycle(tmp_path):
    """Test safe object persistence, retrieval, and deletion in local storage."""
    provider = LocalStorageProvider(base_dir=tmp_path, signing_secret="test-secret-key-1234")

    # Store
    key = "media/user1/test_image.jpg"
    data = b"fake-jpeg-data"
    stored_key = await provider.store_object(key, data, "image/jpeg")
    assert stored_key == key

    # Retrieve
    retrieved = await provider.retrieve_object(key)
    assert retrieved == data

    # Delete
    deleted = await provider.delete_object(key)
    assert deleted is True

    # Non-existent delete
    assert await provider.delete_object(key) is False


@pytest.mark.asyncio
async def test_local_storage_traversal_protection(tmp_path):
    """Ensure path traversal attacks are blocked."""
    provider = LocalStorageProvider(base_dir=tmp_path, signing_secret="test-secret-key-1234")

    with pytest.raises(ValueError, match="Path traversal detected"):
        await provider.store_object("../../etc/passwd", b"bad", "text/plain")


@pytest.mark.asyncio
async def test_local_storage_signed_urls(tmp_path):
    """Verify HMAC token generation and verification."""
    provider = LocalStorageProvider(base_dir=tmp_path, signing_secret="test-secret-key-1234")
    key = "media/u1/pic.jpg"

    url = provider.generate_signed_url(key, expires_in_seconds=60)
    assert "/api/v1/ocr/assets/view?key=" in url
    assert "&exp=" in url
    assert "&sig=" in url

    # Parse query params
    parts = url.split("?")[1].split("&")
    params = dict(p.split("=") for p in parts)
    exp = int(params["exp"])
    sig = params["sig"]

    # Valid verification
    assert provider.verify_token(key, exp, sig) is True

    # Tampered signature
    assert provider.verify_token(key, exp, "bad-signature") is False

    # Expired token
    assert provider.verify_token(key, int(time.time()) - 10, sig) is False


# ==============================================================================
# 2. OCR ADAPTER UNIT TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_mock_ocr_adapter():
    """Verify MockOCRAdapter produces structured result and respects overrides."""
    adapter = MockOCRAdapter()
    result = await adapter.extract_text(b"some-image-bytes", "image/jpeg")
    assert "Aqua / Water" in result.raw_text
    assert result.confidence_score is not None
    assert result.confidence_score > 0.9

    # Custom text
    custom_adapter = MockOCRAdapter(canned_text="INGREDIENTS: Glycerin, Dimethicone.")
    custom_result = await custom_adapter.extract_text(b"any", "image/png")
    assert custom_result.raw_text == "INGREDIENTS: Glycerin, Dimethicone."


@pytest.mark.asyncio
async def test_tesseract_adapter_missing_binary(monkeypatch):
    """Verify LocalTesseractOCRAdapter cleanly reports unavailable when binary missing."""
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    adapter = LocalTesseractOCRAdapter(cmd_path="non_existent_tesseract")
    assert adapter.is_available is False

    with pytest.raises(LocalOCRNotAvailableError, match="Local Tesseract binary not installed"):
        await adapter.extract_text(b"image", "image/jpeg")


@pytest.mark.asyncio
async def test_ocr_space_adapter_success(monkeypatch):
    """Verify OCRSpaceAdapter parses official OCR.space JSON structure."""
    fake_response_data = {
        "ParsedResults": [
            {
                "ParsedText": "Aqua, Niacinamide, Glycerin, Phenoxyethanol",
                "FileParseExitCode": 1,
            }
        ],
        "OCRExitCode": 1,
        "IsErroredOnProcessing": False,
        "ProcessingTimeInMilliseconds": "342",
    }

    async def mock_post(*_args, **_kwargs):
        class MockResponse:
            status_code = 200

            def json(self):
                return fake_response_data

        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    adapter = OCRSpaceAdapter(api_key="test-api-key")
    result = await adapter.extract_text(b"img-bytes", "image/jpeg")
    assert result.raw_text == "Aqua, Niacinamide, Glycerin, Phenoxyethanol"
    assert result.processing_time_ms == 342


@pytest.mark.asyncio
async def test_ocr_space_adapter_rate_limit(monkeypatch):
    """Verify OCRSpaceAdapter handles rate limit (HTTP 429)."""

    async def mock_post(*_args, **_kwargs):
        class MockResponse:
            status_code = 429
            text = "Too Many Requests"

        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    adapter = OCRSpaceAdapter(api_key="test-api-key")
    with pytest.raises(OCRRateLimitError):
        await adapter.extract_text(b"img-bytes", "image/jpeg")


@pytest.mark.asyncio
async def test_ocr_space_adapter_server_error(monkeypatch):
    """Verify OCRSpaceAdapter handles upstream server errors (HTTP 500)."""

    async def mock_post(*_args, **_kwargs):
        class MockResponse:
            status_code = 500
            text = "Internal Server Error"

        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    adapter = OCRSpaceAdapter(api_key="test-api-key")
    with pytest.raises(OCRUnavailableError):
        await adapter.extract_text(b"img-bytes", "image/jpeg")


@pytest.mark.asyncio
async def test_ocr_space_adapter_processing_error(monkeypatch):
    """Verify OCRSpaceAdapter handles error flags inside JSON response."""
    fake_response_data = {
        "ParsedResults": [],
        "OCRExitCode": 3,
        "IsErroredOnProcessing": True,
        "ErrorMessage": ["Unable to recognize image format or text unreadable"],
    }

    async def mock_post(*_args, **_kwargs):
        class MockResponse:
            status_code = 200

            def json(self):
                return fake_response_data

        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    adapter = OCRSpaceAdapter(api_key="test-api-key")
    with pytest.raises(OCRExtractionError):
        await adapter.extract_text(b"img-bytes", "image/jpeg")


# ==============================================================================
# 3. API WORKFLOW & IMAGE VALIDATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_upload_image_validation_empty_file(client: httpx.AsyncClient):
    """Reject empty image upload with 422."""
    token = await register_and_get_token(client, "empty_file_user@example.com")

    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    resp = await client.post(
        "/api/v1/ocr/scans",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "empty" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_upload_image_validation_corrupted_data(client: httpx.AsyncClient):
    """Reject invalid non-image payload with 422."""
    token = await register_and_get_token(client, "corrupt_user@example.com")

    files = {"file": ("corrupt.jpg", b"definitely not an image header", "image/jpeg")}
    resp = await client.post(
        "/api/v1/ocr/scans",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "invalid or corrupted" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_upload_image_validation_dimensions_too_large(client: httpx.AsyncClient):
    """Reject images exceeding maximum dimension limit (4096px)."""
    token = await register_and_get_token(client, "oversized_dim_user@example.com")

    # Generate image with width 4100px
    oversized_img = create_test_image_bytes(size=(4100, 100))
    files = {"file": ("large_dim.jpg", oversized_img, "image/jpeg")}
    resp = await client.post(
        "/api/v1/ocr/scans",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "exceed maximum allowed dimension" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_api_upload_scan_end_to_end(client: httpx.AsyncClient):
    """Upload valid product label, extract candidates, verify signed URL and streaming."""
    token = await register_and_get_token(client, "scan_user1@example.com")

    img_bytes = create_test_image_bytes(format="JPEG", size=(300, 300))
    files = {"file": ("label.jpg", img_bytes, "image/jpeg")}

    resp = await client.post(
        "/api/v1/ocr/scans",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    data = resp.json()["data"]
    assert data["status"] == "succeeded"
    assert data["raw_text"] is not None
    assert len(data["candidates"]) > 0
    assert data["candidate_count"] == len(data["candidates"])

    scan_id = data["id"]
    media_asset = data["media_asset"]
    assert media_asset["content_type"] == "image/jpeg"
    assert media_asset["image_width"] == 300
    assert media_asset["image_height"] == 300
    assert media_asset["view_url"] is not None

    # Verify viewing signed URL streams the image
    view_url = media_asset["view_url"]
    view_resp = await client.get(view_url)
    assert view_resp.status_code == 200
    assert view_resp.headers["content-type"] == "image/jpeg"
    assert view_resp.content == img_bytes

    # Retrieve scan by ID
    get_resp = await client.get(
        f"/api/v1/ocr/scans/{scan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == scan_id


@pytest.mark.asyncio
async def test_api_upload_idempotency(client: httpx.AsyncClient):
    """Submitting the same idempotency key returns existing scan without duplicate processing."""
    token = await register_and_get_token(client, "idempotent_scan_user@example.com")

    img_bytes = create_test_image_bytes(format="PNG", size=(200, 200))
    files = {"file": ("product.png", img_bytes, "image/png")}
    data_payload = {"idempotency_key": "unique-scan-req-12345"}

    resp1 = await client.post(
        "/api/v1/ocr/scans",
        files=files,
        data=data_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 201
    scan1_id = resp1.json()["data"]["id"]

    # Re-upload with same key
    files2 = {"file": ("product.png", img_bytes, "image/png")}
    resp2 = await client.post(
        "/api/v1/ocr/scans",
        files=files2,
        data=data_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 201
    assert resp2.json()["data"]["id"] == scan1_id


@pytest.mark.asyncio
async def test_api_strict_cross_user_scan_isolation(client: httpx.AsyncClient):
    """User B cannot view or confirm scans belonging to User A (strict 404)."""
    user_a_token = await register_and_get_token(client, "user_a_ocr@example.com")
    user_b_token = await register_and_get_token(client, "user_b_ocr@example.com")

    # User A creates scan
    img_bytes = create_test_image_bytes()
    resp = await client.post(
        "/api/v1/ocr/scans",
        files={"file": ("label.jpg", img_bytes, "image/jpeg")},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    scan_id = resp.json()["data"]["id"]

    # User B attempts to GET scan
    get_resp = await client.get(
        f"/api/v1/ocr/scans/{scan_id}",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert get_resp.status_code == 404

    # User B attempts to confirm scan
    confirm_resp = await client.post(
        f"/api/v1/ocr/scans/{scan_id}/confirm",
        json={"ingredients": [{"position": 1, "name": "Glycerin", "is_confirmed": True}]},
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert confirm_resp.status_code == 404


@pytest.mark.asyncio
async def test_api_confirm_scan_workflow(client: httpx.AsyncClient):
    """User can review and confirm candidate ingredients."""
    token = await register_and_get_token(client, "confirm_user@example.com")

    img_bytes = create_test_image_bytes()
    resp = await client.post(
        "/api/v1/ocr/scans",
        files={"file": ("label.jpg", img_bytes, "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    scan_data = resp.json()["data"]
    scan_id = scan_data["id"]
    candidates = scan_data["candidates"]
    assert len(candidates) >= 2

    # User reviews candidates: edits name of first, confirms second, adds a new one
    confirm_payload = {
        "ingredients": [
            {
                "candidate_id": candidates[0]["id"],
                "position": 1,
                "name": "Water (Purified)",
                "is_confirmed": True,
            },
            {
                "candidate_id": candidates[1]["id"],
                "position": 2,
                "name": candidates[1]["normalized_name"],
                "is_confirmed": True,
            },
            {
                "candidate_id": None,
                "position": 3,
                "name": "Tocopherol",
                "is_confirmed": True,
            },
        ]
    }

    confirm_resp = await client.post(
        f"/api/v1/ocr/scans/{scan_id}/confirm",
        json=confirm_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()["data"]
    assert confirm_data["status"] == "confirmed"
    assert confirm_data["confirmed_count"] == 3

    confirmed_candidates = [c for c in confirm_data["candidates"] if c["is_confirmed"]]
    assert len(confirmed_candidates) == 3
    assert confirmed_candidates[0]["normalized_name"] == "Water (Purified)"
    assert confirmed_candidates[0]["is_user_corrected"] is True
    assert confirmed_candidates[0]["is_confirmed"] is True
    assert confirmed_candidates[2]["normalized_name"] == "Tocopherol"


@pytest.mark.asyncio
async def test_catalog_matching_during_scan(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
):
    """Candidate ingredient automatically links to canonical catalog entity if present."""
    token = await register_and_get_token(client, "catalog_match_user@example.com")

    # Insert a canonical ingredient into DB
    canonical = Ingredient(
        inci_name="Niacinamide",
        common_name="Vitamin B3",
        description="Vitamin B3",
    )
    test_session.add(canonical)
    await test_session.commit()
    await test_session.refresh(canonical)

    # Perform scan
    img_bytes = create_test_image_bytes()
    resp = await client.post(
        "/api/v1/ocr/scans",
        files={"file": ("label.jpg", img_bytes, "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    candidates = resp.json()["data"]["candidates"]
    matched = [c for c in candidates if c["normalized_name"].lower() == "niacinamide"]
    assert len(matched) == 1
    assert matched[0]["matched_ingredient_id"] == str(canonical.id)


@pytest.mark.asyncio
async def test_asset_view_token_security(client: httpx.AsyncClient):
    """Asset viewer rejects expired or tampered signatures with 403."""
    # Tampered signature
    resp = await client.get("/api/v1/ocr/assets/view?key=media/u1/1.jpg&exp=9999999999&sig=invalid")
    assert resp.status_code == 403

    # Expired token
    resp_exp = await client.get("/api/v1/ocr/assets/view?key=media/u1/1.jpg&exp=1000&sig=invalid")
    assert resp_exp.status_code == 403
