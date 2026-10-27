"""Abstract OCR provider interface and results schema."""

from abc import abstractmethod
from dataclasses import dataclass

from app.providers.base import BaseProvider


class OCRError(Exception):
    """Base exception for all OCR operations."""

    pass


class OCRRateLimitError(OCRError):
    """Raised when upstream OCR provider rate limits requests (HTTP 429)."""

    pass


class OCRUnavailableError(OCRError):
    """Raised when OCR provider is unreachable or times out."""

    pass


class OCRExtractionError(OCRError):
    """Raised when OCR service encounters unparseable or corrupted image data."""

    pass


class LocalOCRNotAvailableError(OCRError):
    """Raised when local OCR engine binary (e.g. Tesseract) is not installed on host."""

    pass


@dataclass(frozen=True)
class OCRResult:
    """Standardized result returned by any OCR adapter."""

    raw_text: str
    provider: str
    confidence_score: float | None = None
    processing_time_ms: int | None = None


class BaseOCRAdapter(BaseProvider):
    """Abstract interface for replaceable OCR engines."""

    @abstractmethod
    async def extract_text(
        self,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> OCRResult:
        """Extract untrusted raw text from image bytes."""
        pass
