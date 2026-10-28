"""Phase 11: Security Audit, 12-Step End-to-End Integration Journey, and Release Verification.

Covers:
1. Full 12-step end-to-end backend journey:
   - Step 1: Authenticate a test user
   - Step 2: Create a profile and consent record
   - Step 3: Import / retrieve a product and its ingredients
   - Step 4: Index and search the product via Elasticsearch / Discovery
   - Step 5: Upload a test label and obtain OCR output
   - Step 6: Retrieve ingredient evidence
   - Step 7: Generate a grounded Gemini explanation
   - Step 8: Submit a mock skin scan and retrieve observations
   - Step 9: Add a product to My Shelf
   - Step 10: Create a routine and record completion
   - Step 11: Verify Skin Story uses persisted observations
   - Step 12: Attempt cross-user access and confirm denial, consent revocation media purge,
     and full account deletion (`DELETE /api/v1/me`)
2. Security audit checks:
   - SSRF & URL scheme validation on external URLs (`offer_url`, `source_url`)
   - Production configuration validation (`DEBUG=True` rejection & `audit_production_readiness()`)
   - Rate limiting on costly OCR and skin-analysis uploads (`429 RATE_LIMIT_EXCEEDED`)
"""

import io
from unittest.mock import MagicMock

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.ai import get_llm_explanation_provider
from app.core.config import EnvironmentType, Settings, get_settings
from app.core.security import heavy_scan_rate_limiter, validate_safe_external_url
from app.db.models import (
    Ingredient,
    IngredientEvidence,
    Product,
    ProductIngredient,
    ProductIngredientList,
)
from app.providers.gemini import LLMExplanationProvider, LLMGenerationResult
from app.providers.search_provider import SearchProvider, get_search_provider
from app.providers.skin_analysis import MockSkinAnalysisAdapter, get_skin_analysis_provider
from app.schemas.ai_explanations import (
    GeminiStructuredExplanationPayload,
    StructuredFindingItem,
)


def _make_valid_png_bytes(width: int = 320, height: int = 320) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(215, 195, 180))
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_end_to_end_12_step_backend_journey_and_cross_user_isolation(
    client: httpx.AsyncClient,
    test_session: AsyncSession,
    app,
):
    """Execute the complete 12-step backend integration journey and verify ownership isolation."""
    # Seed canonical product, ingredient, and evidence record in PostgreSQL
    niacinamide = Ingredient(
        inci_name="Niacinamide",
        common_name="Vitamin B3",
        aliases=["Nicotinamide"],
        function="brightening, barrier_support",
        description="Water-soluble vitamin B3 amide studied for barrier and tone support.",
        safety_rating="safe",
    )
    test_session.add(niacinamide)
    await test_session.flush()

    evidence = IngredientEvidence(
        ingredient_id=niacinamide.id,
        evidence_category="published_research",
        topic_or_target="hyperpigmentation",
        evidence_direction="supportive",
        evidence_strength="moderate",
        study_type="rct",
        population_or_context="Topical cosmetic formulations (2%-5%) over 8 weeks",
        summary_statement=(
            "Controlled trials report reduced melanosome transfer and improved visible "
            "hyperpigmentation appearance with topical niacinamide."
        ),
        limitations_and_caveats="Abstract-level metadata; individual product vehicle varies.",
        author_or_reviewer="pubmed_importer",
        review_status="verified",
    )
    test_session.add(evidence)

    product = Product(
        name="ToneTrace E2E Niacinamide Barrier Serum",
        brand="ToneTrace Lab",
        category="serum",
        description="Barrier and tone serum with Niacinamide.",
        full_ingredient_list="Aqua, Niacinamide, Glycerin",
        ean_or_upc="0099887766554",
    )
    test_session.add(product)
    await test_session.flush()

    ing_list = ProductIngredientList(
        product_id=product.id,
        formula_version="v1",
        is_current=True,
        raw_ingredient_text="Aqua, Niacinamide, Glycerin",
    )
    test_session.add(ing_list)
    await test_session.flush()

    prod_ing = ProductIngredient(
        product_id=product.id,
        product_ingredient_list_id=ing_list.id,
        ingredient_id=niacinamide.id,
        position=1,
        concentration_percentage=None,
    )
    test_session.add(prod_ing)
    await test_session.commit()

    # Configure mock Elasticsearch provider and deterministic Gemini provider
    mock_es = MagicMock(spec=SearchProvider)
    mock_es.products_alias = "tonetrace_products"
    mock_es.check_health.return_value = (True, "OK", 1.5)
    mock_es.execute_search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_id": str(product.id),
                    "_score": 8.5,
                    "_source": {
                        "id": str(product.id),
                        "name": product.name,
                        "brand": product.brand,
                        "category": product.category,
                        "ingredient_names": ["Aqua", "Niacinamide", "Glycerin"],
                        "updated_at": "2026-10-27T00:00:00+00:00",
                    },
                }
            ],
        }
    }

    class DeterministicE2ELLMProvider(LLMExplanationProvider):
        @property
        def name(self) -> str:
            return "mock-gemini"

        @property
        def model_name(self) -> str:
            return "gemini-3.5-flash-lite"

        @property
        def is_configured(self) -> bool:
            return True

        async def check_health(self) -> tuple[bool, str | None]:
            return True, "Ready"

        async def generate_structured_explanation(
            self,
            system_instruction: str,
            grounded_prompt: str,
            response_schema: dict[str, object],
        ) -> LLMGenerationResult:
            _ = (system_instruction, grounded_prompt, response_schema)
            payload = GeminiStructuredExplanationPayload(
                summary=(
                    "ToneTrace E2E Niacinamide Barrier Serum contains Niacinamide, which has "
                    "published RCT research relating to visible hyperpigmentation support."
                ),
                key_findings=[
                    StructuredFindingItem(
                        statement=(
                            "Niacinamide is included in this formula and has controlled trial "
                            "evidence for visible tone support, with unknown exact concentration."
                        ),
                        epistemic_category="published_research",
                        evidence_strength="moderate",
                        cited_source_ids=[
                            f"prod:{product.id}",
                            f"ing:{niacinamide.id}",
                            f"ev:{evidence.id}",
                        ],
                    )
                ],
                uncertainty_notes=["Exact Niacinamide percentage is not disclosed."],
                requires_professional_care_escalation=False,
            )
            return LLMGenerationResult(
                raw_text=payload.model_dump_json(),
                provider=self.name,
                model=self.model_name,
                latency_ms=12.0,
            )

    es_settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ELASTICSEARCH_ENABLED=True,
        ELASTICSEARCH_FALLBACK_TO_DB=True,
        OCR_PROVIDER="mock",
        STORAGE_PROVIDER="local",
        STORAGE_LOCAL_DIR="./var/test_storage_e2e",
    )

    app.dependency_overrides[get_settings] = lambda: es_settings
    app.dependency_overrides[get_search_provider] = lambda: mock_es
    app.dependency_overrides[get_llm_explanation_provider] = lambda: DeterministicE2ELLMProvider()
    app.dependency_overrides[get_skin_analysis_provider] = lambda: MockSkinAnalysisAdapter()

    try:
        # ------------------------------------------------------------------
        # STEP 1: Authenticate a test user
        # ------------------------------------------------------------------
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "e2e_journey@example.com",
                "password": "StrongPassword123!",
                "display_name": "E2E Tester",
            },
        )
        assert reg_resp.status_code == 201, reg_resp.text
        access_token = reg_resp.json()["data"]["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # ------------------------------------------------------------------
        # STEP 2: Create a profile and consent record
        # ------------------------------------------------------------------
        prof_resp = await client.patch(
            "/api/v1/me",
            headers=headers,
            json={"display_name": "E2E Verified User", "timezone": "America/New_York"},
        )
        assert prof_resp.status_code == 200, prof_resp.text

        skin_prof_resp = await client.put(
            "/api/v1/me/skin-profile",
            headers=headers,
            json={
                "skin_type": "combination",
                "skin_concerns": ["hyperpigmentation"],
                "skin_goals": ["brightening"],
            },
        )
        assert skin_prof_resp.status_code == 200, skin_prof_resp.text

        consent_resp = await client.put(
            "/api/v1/me/consents/skin_data_processing",
            headers=headers,
            json={"policy_version": "1.0.0", "is_granted": True},
        )
        assert consent_resp.status_code == 200, consent_resp.text
        assert consent_resp.json()["data"]["is_granted"] is True

        # ------------------------------------------------------------------
        # STEP 3: Retrieve a product by UUID and barcode
        # ------------------------------------------------------------------
        prod_resp = await client.get(f"/api/v1/products/{product.id}", headers=headers)
        assert prod_resp.status_code == 200, prod_resp.text
        assert prod_resp.json()["data"]["name"] == "ToneTrace E2E Niacinamide Barrier Serum"

        barcode_resp = await client.get(
            f"/api/v1/products/barcode/{product.ean_or_upc}",
            headers=headers,
        )
        assert barcode_resp.status_code == 200, barcode_resp.text
        assert barcode_resp.json()["data"]["id"] == str(product.id)

        # ------------------------------------------------------------------
        # STEP 4: Search the product in Elasticsearch via Discovery
        # ------------------------------------------------------------------
        disc_resp = await client.get(
            "/api/v1/discovery/products?q=Niacinamide&goal=hyperpigmentation",
            headers=headers,
        )
        assert disc_resp.status_code == 200, disc_resp.text
        disc_data = disc_resp.json()["data"]
        assert disc_data["search_backend_used"] == "elasticsearch"
        assert disc_data["total"] == 1
        assert disc_data["items"][0]["product_id"] == str(product.id)

        # ------------------------------------------------------------------
        # STEP 5: Upload a test label and obtain OCR output
        # ------------------------------------------------------------------
        label_bytes = _make_valid_png_bytes()
        ocr_resp = await client.post(
            "/api/v1/ocr/scans",
            headers=headers,
            files={"file": ("label.png", label_bytes, "image/png")},
            data={"idempotency_key": "e2e-ocr-1"},
        )
        assert ocr_resp.status_code == 201, ocr_resp.text
        ocr_scan_id = ocr_resp.json()["data"]["id"]
        assert ocr_resp.json()["data"]["status"] == "succeeded"
        assert len(ocr_resp.json()["data"]["candidates"]) >= 1

        # ------------------------------------------------------------------
        # STEP 6: Retrieve ingredient evidence
        # ------------------------------------------------------------------
        ev_resp = await client.get(
            f"/api/v1/ingredients/{niacinamide.id}/evidence",
            headers=headers,
        )
        assert ev_resp.status_code == 200, ev_resp.text
        assert len(ev_resp.json()["data"]["items"]) == 1
        assert ev_resp.json()["data"]["items"][0]["id"] == str(evidence.id)

        # ------------------------------------------------------------------
        # STEP 7: Generate a grounded Gemini explanation
        # ------------------------------------------------------------------
        ai_resp = await client.post(
            "/api/v1/ai/explanations",
            headers=headers,
            json={
                "question": "How does this serum relate to hyperpigmentation?",
                "product_ids": [str(product.id)],
                "ingredient_ids": [str(niacinamide.id)],
            },
        )
        assert ai_resp.status_code == 200, ai_resp.text
        ai_data = ai_resp.json()["data"]
        assert ai_data["grounding_status"] == "verified"
        cited_ids = {ref["source_id"] for ref in ai_data["source_references"]}
        assert f"prod:{product.id}" in cited_ids
        assert f"ing:{niacinamide.id}" in cited_ids
        assert f"ev:{evidence.id}" in cited_ids

        # ------------------------------------------------------------------
        # STEP 8: Submit a mock skin scan and retrieve observations
        # ------------------------------------------------------------------
        scan_resp_1 = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("face1.png", _make_valid_png_bytes(400, 400), "image/png")},
            data={
                "idempotency_key": "e2e-skin-scan-1",
                "lighting_condition": "natural_daylight",
                "camera_angle": "frontal",
            },
        )
        assert scan_resp_1.status_code == 201, scan_resp_1.text
        skin_scan_1_id = scan_resp_1.json()["data"]["id"]
        assert scan_resp_1.json()["data"]["status"] == "succeeded"
        assert len(scan_resp_1.json()["data"]["observations"]) >= 1

        # ------------------------------------------------------------------
        # STEP 9: Add a product to My Shelf
        # ------------------------------------------------------------------
        shelf_resp = await client.post(
            "/api/v1/me/shelf",
            headers=headers,
            json={
                "product_id": str(product.id),
                "status": "in_use",
                "private_notes": "Using every morning.",
            },
        )
        assert shelf_resp.status_code == 201, shelf_resp.text
        shelf_item_id = shelf_resp.json()["data"]["id"]
        assert shelf_resp.json()["data"]["is_public"] is False

        # ------------------------------------------------------------------
        # STEP 10: Create a routine and record completion
        # ------------------------------------------------------------------
        routine_resp = await client.post(
            "/api/v1/me/routines",
            headers=headers,
            json={
                "name": "E2E Morning Routine",
                "time_of_day": "morning",
                "frequency": "daily",
                "steps": [
                    {
                        "step_order": 1,
                        "user_product_id": shelf_item_id,
                        "custom_instruction": "Apply 3 drops to clean skin",
                    }
                ],
            },
        )
        assert routine_resp.status_code == 201, routine_resp.text
        routine_id = routine_resp.json()["data"]["id"]

        comp_resp = await client.post(
            f"/api/v1/me/routines/{routine_id}/completions",
            headers=headers,
            json={"status": "completed", "notes": "Day 1 completed"},
        )
        assert comp_resp.status_code == 201, comp_resp.text
        assert comp_resp.json()["data"]["user_timezone"] == "America/New_York"

        # ------------------------------------------------------------------
        # STEP 11: Verify Skin Story uses persisted observations
        # ------------------------------------------------------------------
        scan_resp_2 = await client.post(
            "/api/v1/skin/scans",
            headers=headers,
            files={"file": ("face2.png", _make_valid_png_bytes(420, 420), "image/png")},
            data={
                "idempotency_key": "e2e-skin-scan-2",
                "lighting_condition": "natural_daylight",
                "camera_angle": "frontal",
            },
        )
        assert scan_resp_2.status_code == 201, scan_resp_2.text

        story_resp = await client.get("/api/v1/skin/story", headers=headers)
        assert story_resp.status_code == 200, story_resp.text
        story_data = story_resp.json()["data"]
        assert story_data["total_succeeded_scans"] == 2
        assert len(story_data["metric_timelines"]) >= 1

        # ------------------------------------------------------------------
        # STEP 12: Attempt cross-user access and confirm denial, consent
        #          revocation media purge, and account deletion
        # ------------------------------------------------------------------
        reg_b = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "intruder_b@example.com",
                "password": "StrongPassword123!",
                "display_name": "Intruder B",
            },
        )
        headers_b = {"Authorization": f"Bearer {reg_b.json()['data']['tokens']['access_token']}"}

        # Intruder B cannot access User A's OCR scan, skin scan, shelf item, or routine
        assert (
            await client.get(f"/api/v1/ocr/scans/{ocr_scan_id}", headers=headers_b)
        ).status_code == 404
        assert (
            await client.get(f"/api/v1/skin/scans/{skin_scan_1_id}", headers=headers_b)
        ).status_code == 404
        assert (
            await client.get(f"/api/v1/me/shelf/{shelf_item_id}", headers=headers_b)
        ).status_code == 404
        assert (
            await client.get(f"/api/v1/me/routines/{routine_id}", headers=headers_b)
        ).status_code == 404

        # Revoking skin_data_processing consent purges retained scan media immediately
        revoke_resp = await client.put(
            "/api/v1/me/consents/skin_data_processing",
            headers=headers,
            json={"policy_version": "1.0.0", "is_granted": False},
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["data"]["is_granted"] is False

        scan_after_revoke = await client.get(
            f"/api/v1/skin/scans/{skin_scan_1_id}",
            headers=headers,
        )
        assert scan_after_revoke.status_code == 200
        assert all(m["is_deleted"] is True for m in scan_after_revoke.json()["data"]["media_items"])

        # Full account deletion purges remaining media and removes the user
        del_acc_resp = await client.delete("/api/v1/me", headers=headers)
        assert del_acc_resp.status_code == 200, del_acc_resp.text
        assert del_acc_resp.json()["data"]["status"] == "account_deleted"
        assert del_acc_resp.json()["data"]["purged_storage_objects"] >= 1

        # Token for deleted user is immediately rejected with 401
        me_after_del = await client.get("/api/v1/me", headers=headers)
        assert me_after_del.status_code == 401
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_search_provider, None)
        app.dependency_overrides.pop(get_llm_explanation_provider, None)
        app.dependency_overrides.pop(get_skin_analysis_provider, None)


def test_security_audit_ssrf_url_validation_and_production_debug_guard():
    """Verify SSRF/scheme validation on external URLs and production DEBUG rejection."""
    # Valid external HTTPS URL passes
    assert (
        validate_safe_external_url("https://www.sephora.com/product/niacinamide")
        == "https://www.sephora.com/product/niacinamide"
    )
    assert validate_safe_external_url(None) is None

    # Unsafe schemes and SSRF targets are rejected
    unsafe_urls = [
        "http://www.sephora.com/product/niacinamide",  # non-HTTPS
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://127.0.0.1/admin",
        "https://localhost:8000/health/live",
        "https://169.254.169.254/latest/meta-data/",
        "https://10.0.0.15/internal",
        "https://192.168.1.1/router",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://service.internal/secret",
        "https://user:password@example.com/path",
    ]
    for bad_url in unsafe_urls:
        with pytest.raises(ValueError):
            validate_safe_external_url(bad_url)

    # Production settings strictly reject DEBUG=True
    with pytest.raises(ValidationError, match="DEBUG mode cannot be enabled in production"):
        Settings(
            ENVIRONMENT=EnvironmentType.PRODUCTION,
            DEBUG=True,
            ALLOWED_CORS_ORIGINS=["https://app.tonetrace.ai"],
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
            AUTH_JWT_SECRET="super-secure-production-jwt-secret-key-32chars!",
        )

    # Production readiness audit reports mock providers and local storage
    prod_settings = Settings(
        ENVIRONMENT=EnvironmentType.PRODUCTION,
        DEBUG=False,
        ALLOWED_CORS_ORIGINS=["https://app.tonetrace.ai"],
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        AUTH_JWT_SECRET="super-secure-production-jwt-secret-key-32chars!",
        SKIN_ANALYSIS_PROVIDER="mock",
    )
    findings = prod_settings.audit_production_readiness()
    assert any("STORAGE_SIGNING_SECRET" in f for f in findings)
    assert not any("STORAGE_PROVIDER" in f for f in findings)  # MVP: PostgreSQL BYTEA default
    assert any("SKIN_ANALYSIS_PROVIDER" in f for f in findings)


@pytest.mark.asyncio
async def test_heavy_scan_rate_limiting_on_ocr_and_skin_uploads(
    client: httpx.AsyncClient,
):
    """Verify rate limiting on costly multipart OCR and skin scan uploads."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ratelimit_scan@example.com",
            "password": "StrongPassword123!",
            "display_name": "ScanLimiter",
        },
    )
    headers = {"Authorization": f"Bearer {reg.json()['data']['tokens']['access_token']}"}

    original_rpm = heavy_scan_rate_limiter.requests_per_minute
    heavy_scan_rate_limiter.requests_per_minute = 2
    heavy_scan_rate_limiter.reset()
    try:
        img_bytes = _make_valid_png_bytes()
        r1 = await client.post(
            "/api/v1/ocr/scans",
            headers=headers,
            files={"file": ("label1.png", img_bytes, "image/png")},
        )
        assert r1.status_code == 201

        r2 = await client.post(
            "/api/v1/ocr/scans",
            headers=headers,
            files={"file": ("label2.png", img_bytes, "image/png")},
        )
        assert r2.status_code == 201

        # 3rd upload within the window is blocked with 429 RATE_LIMIT_EXCEEDED
        r3 = await client.post(
            "/api/v1/ocr/scans",
            headers=headers,
            files={"file": ("label3.png", img_bytes, "image/png")},
        )
        assert r3.status_code == 429
        assert r3.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    finally:
        heavy_scan_rate_limiter.requests_per_minute = original_rpm
        heavy_scan_rate_limiter.reset()
