"""Google Gemini Vision OCR adapter using `google-genai` SDK.

Implements cosmetic package and label optical character recognition using
Google Gemini multimodal vision models (e.g. gemini-2.5-flash or gemini-3.5-flash-lite).
Extracted text is strictly formatted as comma-separated cosmetic INCI ingredients,
filtering out non-ingredient marketing copy, instructions, and batch numbers.
"""

import asyncio
import logging
import time
from typing import Any

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.providers.ocr.base import (
    BaseOCRAdapter,
    OCRExtractionError,
    OCRRateLimitError,
    OCRResult,
    OCRUnavailableError,
)

logger = logging.getLogger(__name__)

GEMINI_OCR_SYSTEM_PROMPT = """You are an expert optical character recognition (OCR) and cosmetic packaging label reading specialist.
Your task is to accurately transcribe the cosmetic formulation ingredients printed on the packaging image.

Rules:
1. Locate the INCI / ingredients list on the packaging (often preceded by "INGREDIENTS:", "CONTENTS:", or "ACTIVE INGREDIENTS:").
2. Extract all ingredient names in order, separated by commas.
3. Correct obvious typographical or character recognition artifacts caused by curved bottle surfaces, reflections, or decorative typography.
4. Omit non-ingredient marketing copy, instructions for use, warning statements, distributor addresses, batch codes, and volume text (e.g., "50ml", "Dermatologist Tested", "Made in USA", "Directions: Apply generously").
5. Return ONLY the comma-separated ingredient list as plain text. Do not wrap in markdown quotes, JSON, or additional commentary.
"""


class GeminiOCRAdapter(BaseOCRAdapter):
    """Google Gemini Vision OCR adapter using the official `google-genai` SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 30.0,
        genai_client: genai.Client | None = None,
    ) -> None:
        settings = get_settings()
        resolved_key = (
            api_key
            or (settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None)
        )
        self._api_key = resolved_key
        # Default to configured GEMINI_MODEL or gemini-2.5-flash
        self._model = (model or settings.GEMINI_MODEL or "gemini-2.5-flash").strip()
        self._timeout_seconds = timeout_seconds
        self._client = genai_client

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def _get_client(self) -> genai.Client:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise OCRUnavailableError(
                "Gemini OCR is not configured. Supply a valid GEMINI_API_KEY in the environment."
            )
        return genai.Client(api_key=self._api_key)

    async def check_health(self) -> tuple[bool, str | None]:
        if not self.is_configured:
            return False, "GEMINI_API_KEY is not configured for Gemini OCR."
        return True, f"Gemini OCR active using model '{self._model}'."

    async def extract_text(
        self,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> OCRResult:
        """Extract cosmetic ingredients text using Gemini Vision multimodal inference."""
        if not image_bytes:
            raise OCRExtractionError("Empty image bytes provided for Gemini OCR extraction.")

        client = self._get_client()
        start_time = time.perf_counter()

        # Build inline image Part per google-genai SDK
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=content_type or "image/jpeg",
        )

        prompt = (
            "Read and extract the full ingredients list from this cosmetic product packaging label."
        )

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self._model,
                    contents=[image_part, prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=GEMINI_OCR_SYSTEM_PROMPT,
                        temperature=0.1,
                    ),
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError as err:
            logger.error("Gemini OCR extraction timed out after %.1fs", self._timeout_seconds)
            raise OCRUnavailableError(f"Gemini OCR timed out after {self._timeout_seconds}s") from err
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                logger.warning("Gemini OCR rate limit or quota exceeded: %s", exc)
                raise OCRRateLimitError(
                    "Gemini OCR quota or rate limit exceeded. Please try again shortly."
                ) from exc
            logger.error("Gemini OCR request failed: %s", exc)
            raise OCRUnavailableError(f"Gemini OCR error: {exc}") from exc

        raw_text = (response.text or "").strip()
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        if not raw_text:
            raise OCRExtractionError(
                "Gemini Vision was unable to detect or transcribe ingredient text from this image."
            )

        return OCRResult(
            raw_text=raw_text,
            provider=self.name,
            confidence_score=0.95,
            processing_time_ms=elapsed_ms,
        )
