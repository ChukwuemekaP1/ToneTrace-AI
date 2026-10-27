"""OCR.space Online OCR Provider Adapter.

Grounded strictly in verified OCR.space API endpoint contracts:
Endpoint: POST https://api.ocr.space/parse/image
Header: apikey: <API_KEY>
Payload: multipart/form-data with image file bytes
Documentation: https://ocr.space/ocrapi
"""

import logging
import time

import httpx

from app.core.config import get_settings
from app.providers.ocr.base import (
    BaseOCRAdapter,
    OCRExtractionError,
    OCRRateLimitError,
    OCRResult,
    OCRUnavailableError,
)

logger = logging.getLogger(__name__)


class OCRSpaceAdapter(BaseOCRAdapter):
    """Adapter for official OCR.space API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 25.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = (
            api_key
            if api_key is not None
            else (settings.OCR_API_KEY.get_secret_value() if settings.OCR_API_KEY else None)
        )
        self._base_url = (base_url or settings.OCR_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def name(self) -> str:
        return "ocr_space"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    async def check_health(self) -> tuple[bool, str | None]:
        """Check OCR.space connectivity without exposing credentials."""
        if not self.is_configured:
            return False, "OCR.space API key is not configured."
        try:
            # Lightweight probe
            url = self._base_url
            headers = {"apikey": self._api_key}
            data = {"url": "https://dl.a9t9.com/ocrbenchmark/eng.png", "language": "eng"}
            if self._client:
                resp = await self._client.post(url, headers=headers, data=data)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    resp = await client.post(url, headers=headers, data=data)

            if resp.status_code == 200:
                payload = resp.json()
                if payload.get("OCRExitCode") == 1:
                    return True, "OCR.space API reachable and verified."
                return False, f"OCR.space returned error: {payload.get('ErrorMessage')}"
            if resp.status_code == 429:
                return False, "OCR.space rate limit exceeded."
            return False, f"OCR.space returned HTTP {resp.status_code}"
        except Exception as exc:
            logger.warning("OCR.space health check failed: %s", exc)
            return False, f"OCR.space unreachable: {exc}"

    async def extract_text(
        self,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> OCRResult:
        """Extract text from image bytes using OCR.space.

        Uploads file bytes via multipart form data.
        """
        if not self.is_configured:
            raise OCRUnavailableError(
                "OCR.space is unconfigured. Supply OCR_API_KEY in environment."
            )

        start_time = time.perf_counter()
        url = self._base_url
        headers = {"apikey": self._api_key}
        data = {
            "language": "eng",
            "isOverlayRequired": "false",
            "detectOrientation": "true",
            "scale": "true",
            "OCREngine": "2",
        }
        files = {
            "file": ("image.jpg", image_bytes, content_type),
        }

        try:
            if self._client:
                response = await self._client.post(url, headers=headers, data=data, files=files)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, headers=headers, data=data, files=files)

            if response.status_code == 429:
                raise OCRRateLimitError(
                    "OCR.space API rate limit reached. Please back off and retry."
                )
            if response.status_code >= 500:
                raise OCRUnavailableError(f"OCR.space server error: HTTP {response.status_code}")
            if response.status_code != 200:
                raise OCRUnavailableError(
                    f"OCR.space unexpected HTTP status: {response.status_code}"
                )

            payload = response.json()
            is_errored = payload.get("IsErroredOnProcessing", False)
            if is_errored:
                err_msg = payload.get("ErrorMessage") or "Unknown OCR processing error"
                raise OCRExtractionError(f"OCR.space processing failed: {err_msg}")

            parsed_results = payload.get("ParsedResults") or []
            if not parsed_results:
                return OCRResult(
                    raw_text="",
                    provider=self.name,
                    confidence_score=0.0,
                    processing_time_ms=int((time.perf_counter() - start_time) * 1000),
                )

            first_result = parsed_results[0]
            raw_text = first_result.get("ParsedText") or ""
            proc_time = payload.get("ProcessingTimeInMilliseconds")
            proc_ms = (
                int(proc_time)
                if proc_time and str(proc_time).isdigit()
                else int((time.perf_counter() - start_time) * 1000)
            )

            return OCRResult(
                raw_text=raw_text.strip(),
                provider=self.name,
                confidence_score=0.85 if raw_text else 0.0,
                processing_time_ms=proc_ms,
            )

        except (httpx.TimeoutException, httpx.NetworkError) as net_err:
            logger.error("OCR.space network/timeout failure: %s", net_err)
            raise OCRUnavailableError(f"OCR.space connection failed: {net_err}") from net_err
