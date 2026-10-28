"""PostgreSQL BYTEA private storage provider for the ToneTrace AI MVP.

For the hackathon MVP, Neon PostgreSQL is the sole persistent data store.
Validated small image bytes are persisted in `media_assets.image_bytes` (`BYTEA`)
with SQLAlchemy deferred column loading so ordinary queries never return raw image
bytes by default.

Short-lived HMAC-SHA256 signed URLs and authenticated owner-only endpoints are
used to view or delete stored images.
"""

import hashlib
import hmac
import time
from urllib.parse import quote_plus

from app.core.config import get_settings
from app.providers.storage.base import BaseStorageProvider


class PostgresStorageProvider(BaseStorageProvider):
    """PostgreSQL BYTEA storage provider with HMAC-signed URL verification."""

    def __init__(self, signing_secret: str | None = None) -> None:
        settings = get_settings()
        self._signing_secret = (
            signing_secret or settings.STORAGE_SIGNING_SECRET.get_secret_value()
        ).encode("utf-8")

    @property
    def name(self) -> str:
        return "postgres"

    async def store_object(
        self,
        key: str,
        data: bytes,
        _content_type: str,
    ) -> str:
        """No-op at filesystem level; bytes are persisted on `MediaAsset.image_bytes` in DB."""
        _ = data
        if ".." in key or key.startswith(("/", "\\")):
            raise ValueError(f"Invalid storage key: {key}")
        return key

    async def retrieve_object(self, key: str) -> bytes:
        """Direct key retrieval without DB session is unsupported; use DB session lookup."""
        raise FileNotFoundError(
            f"PostgresStorageProvider requires a database session to load BYTEA for key '{key}'."
        )

    async def delete_object(self, key: str) -> bool:
        """No-op at filesystem level; DB service nulls `MediaAsset.image_bytes`."""
        _ = key
        return True

    def generate_signed_url(
        self,
        key: str,
        expires_in_seconds: int = 300,
    ) -> str:
        """Generate a short-lived HMAC-signed URL pointing to `/api/v1/ocr/assets/view`."""
        expires_at = int(time.time()) + expires_in_seconds
        payload = f"{key}:{expires_at}".encode()
        sig = hmac.new(self._signing_secret, payload, hashlib.sha256).hexdigest()

        encoded_key = quote_plus(key)
        settings = get_settings()
        api_prefix = settings.API_V1_PREFIX
        return f"{api_prefix}/ocr/assets/view?key={encoded_key}&exp={expires_at}&sig={sig}"

    def verify_token(self, key: str, expires_at: int, signature: str) -> bool:
        """Verify HMAC-SHA256 signature and expiration timestamp."""
        if time.time() > expires_at:
            return False
        payload = f"{key}:{expires_at}".encode()
        expected_sig = hmac.new(self._signing_secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)
