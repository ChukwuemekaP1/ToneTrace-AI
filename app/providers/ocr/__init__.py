"""OCR provider adapter package."""

from app.core.config import get_settings
from app.providers.ocr.base import (
    BaseOCRAdapter,
    LocalOCRNotAvailableError,
    OCRError,
    OCRExtractionError,
    OCRRateLimitError,
    OCRResult,
    OCRUnavailableError,
)
from app.providers.ocr.gemini import GeminiOCRAdapter
from app.providers.ocr.mock import MockOCRAdapter
from app.providers.ocr.ocr_space import OCRSpaceAdapter
from app.providers.ocr.tesseract import LocalTesseractOCRAdapter


def get_ocr_adapter() -> BaseOCRAdapter:
    """Factory returning configured OCR engine adapter."""
    settings = get_settings()
    provider = settings.OCR_PROVIDER.lower()
    if provider == "gemini":
        return GeminiOCRAdapter()
    if provider == "ocr_space":
        return OCRSpaceAdapter()
    if provider == "tesseract":
        return LocalTesseractOCRAdapter()
    return MockOCRAdapter()


__all__ = [
    "BaseOCRAdapter",
    "GeminiOCRAdapter",
    "LocalOCRNotAvailableError",
    "LocalTesseractOCRAdapter",
    "MockOCRAdapter",
    "OCRError",
    "OCRExtractionError",
    "OCRRateLimitError",
    "OCRResult",
    "OCRSpaceAdapter",
    "OCRUnavailableError",
    "get_ocr_adapter",
]
