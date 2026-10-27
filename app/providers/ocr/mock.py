"""Deterministic mock OCR provider adapter for tests and offline development."""

from app.providers.ocr.base import BaseOCRAdapter, OCRResult


class MockOCRAdapter(BaseOCRAdapter):
    """Deterministic mock OCR engine producing predictable results."""

    def __init__(
        self,
        canned_text: str | None = None,
        confidence_score: float = 0.95,
        processing_time_ms: int = 120,
    ) -> None:
        self.canned_text = (
            canned_text
            if canned_text is not None
            else (
                "INGREDIENTS: Aqua / Water, Glycerin, Dimethicone, Niacinamide, "
                "Ceramide NP, Ceramide AP, Sodium Hyaluronate, Tocopherol, "
                "Phenoxyethanol, Carbomer, Xanthan Gum."
            )
        )
        self.confidence_score = confidence_score
        self.processing_time_ms = processing_time_ms

    @property
    def name(self) -> str:
        return "mock"

    async def check_health(self) -> tuple[bool, str | None]:
        return True, "Mock OCR engine active and deterministic."

    async def extract_text(
        self,
        _image_bytes: bytes,
        _content_type: str = "image/jpeg",
    ) -> OCRResult:
        """Return deterministic extracted text."""
        return OCRResult(
            raw_text=self.canned_text,
            provider=self.name,
            confidence_score=self.confidence_score,
            processing_time_ms=self.processing_time_ms,
        )
