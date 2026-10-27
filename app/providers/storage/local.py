"""Local filesystem private object storage provider.

Secured with HMAC-SHA256 short-lived token generation for asset access.
Guarantees path traversal immunity and private directory containment.
"""

import hashlib
import hmac
import logging
import time
from pathlib import Path
from urllib.parse import quote_plus

from app.core.config import get_settings
from app.providers.storage.base import BaseStorageProvider

logger = logging.getLogger(__name__)


class LocalStorageProvider(BaseStorageProvider):
    """Local filesystem private storage with timed HMAC token verification."""

    def __init__(
        self,
        base_dir: str | Path | None = None,
        signing_secret: str | None = None,
    ) -> None:
        settings = get_settings()
        self._base_dir = Path(base_dir or settings.STORAGE_LOCAL_DIR).resolve()
        self._signing_secret = (
            signing_secret or settings.STORAGE_SIGNING_SECRET.get_secret_value()
        ).encode("utf-8")
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "local"

    def _resolve_safe_path(self, key: str) -> Path:
        """Resolve path ensuring no directory traversal escapes base_dir."""
        # Reject path traversal patterns or absolute targets
        if ".." in Path(key).parts or Path(key).is_absolute() or key.startswith(("/", "\\")):
            raise ValueError(f"Path traversal detected in storage key: {key}")
        full_path = (self._base_dir / key).resolve()
        if not full_path.is_relative_to(self._base_dir):
            raise ValueError(f"Path traversal detected in storage key: {key}")
        return full_path

    async def store_object(
        self,
        key: str,
        data: bytes,
        _content_type: str,
    ) -> str:
        """Persist object bytes securely to local storage."""
        target_path = self._resolve_safe_path(key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)
        return key

    async def retrieve_object(self, key: str) -> bytes:
        """Retrieve stored object bytes."""
        target_path = self._resolve_safe_path(key)
        if not target_path.exists():
            raise FileNotFoundError(f"Storage object '{key}' not found.")
        return target_path.read_bytes()

    async def delete_object(self, key: str) -> bool:
        """Delete stored object if present."""
        try:
            target_path = self._resolve_safe_path(key)
            if target_path.exists():
                target_path.unlink()
                return True
            return False
        except Exception as exc:
            logger.warning("Error deleting local object '%s': %s", key, exc)
            return False

    def generate_signed_url(
        self,
        key: str,
        expires_in_seconds: int = 300,
    ) -> str:
        """Generate a short-lived HMAC-signed viewing URL."""
        expires_at = int(time.time()) + expires_in_seconds
        payload = f"{key}:{expires_at}".encode()
        sig = hmac.new(self._signing_secret, payload, hashlib.sha256).hexdigest()

        encoded_key = quote_plus(key)
        settings = get_settings()
        api_prefix = settings.API_V1_PREFIX
        return f"{api_prefix}/ocr/assets/view?key={encoded_key}&exp={expires_at}&sig={sig}"

    def verify_token(self, key: str, expires_at: int, signature: str) -> bool:
        """Verify HMAC signature and timestamp."""
        if time.time() > expires_at:
            return False
        payload = f"{key}:{expires_at}".encode()
        expected_sig = hmac.new(self._signing_secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)
