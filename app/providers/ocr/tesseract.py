"""Local Tesseract OCR provider adapter.

Checks for local Tesseract binary installation. Raises clear diagnostic
errors if host requirements are not met.
"""

import io
import logging
import shutil
import time

from PIL import Image

from app.core.config import get_settings
from app.providers.ocr.base import (
    BaseOCRAdapter,
    LocalOCRNotAvailableError,
    OCRExtractionError,
    OCRResult,
)

logger = logging.getLogger(__name__)


class LocalTesseractOCRAdapter(BaseOCRAdapter):
    """Local Tesseract OCR engine candidate."""

    def __init__(self, cmd_path: str | None = None) -> None:
        settings = get_settings()
        self._cmd_path = cmd_path or settings.TESSERACT_CMD_PATH

    @property
    def name(self) -> str:
        return "tesseract"

    def _get_binary_path(self) -> str | None:
        cmd = self._cmd_path or "tesseract"
        return shutil.which(cmd)

    @property
    def is_available(self) -> bool:
        """True if Tesseract executable is found on host."""
        return self._get_binary_path() is not None

    async def check_health(self) -> tuple[bool, str | None]:
        """Check if local Tesseract engine is installed and callable."""
        bin_path = self._get_binary_path()
        if not bin_path:
            return False, "Tesseract OCR binary not found on host. Install tesseract-ocr to enable."
        return True, f"Tesseract OCR binary verified at: {bin_path}"

    async def extract_text(
        self,
        image_bytes: bytes,
        _content_type: str = "image/jpeg",
    ) -> OCRResult:
        """Extract text using host Tesseract installation."""
        bin_path = self._get_binary_path()
        if not bin_path:
            raise LocalOCRNotAvailableError(
                "Local Tesseract binary not installed on this system. "
                "Set OCR_PROVIDER=ocr_space or install Tesseract OCR on the host."
            )

        start_time = time.perf_counter()

        try:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = bin_path
            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image)

            proc_ms = int((time.perf_counter() - start_time) * 1000)
            return OCRResult(
                raw_text=text.strip(),
                provider=self.name,
                confidence_score=0.80 if text.strip() else 0.0,
                processing_time_ms=proc_ms,
            )
        except ImportError as exc:
            raise LocalOCRNotAvailableError(
                "pytesseract package not installed. Run 'uv add pytesseract'."
            ) from exc
        except Exception as exc:
            logger.error("Tesseract execution failure: %s", exc)
            raise OCRExtractionError(f"Tesseract failed to parse image: {exc}") from exc
