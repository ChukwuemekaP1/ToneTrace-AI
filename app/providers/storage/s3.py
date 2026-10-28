"""Private S3 / Neon Object Storage compatible provider.

Configured specifically for Neon's S3-compatible Object Storage with:
- forcePathStyle: true (path-style addressing required by Neon)
- Presigned URL generation for time-limited secure viewing without public bucket exposure
- Robust upload and deletion handlers
"""

import logging
from typing import Any

from botocore.client import Config

from app.core.config import get_settings
from app.providers.storage.base import BaseStorageProvider

logger = logging.getLogger(__name__)


class S3StorageProvider(BaseStorageProvider):
    """S3-compatible object storage provider (Neon Object Storage, AWS S3, Cloudflare R2)."""

    def __init__(
        self,
        bucket_name: str | None = None,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        force_path_style: bool | None = None,
    ) -> None:
        settings = get_settings()
        self._bucket_name = bucket_name or settings.STORAGE_BUCKET_NAME
        self._endpoint_url = endpoint_url or settings.STORAGE_ENDPOINT_URL
        self._region_name = region_name or settings.STORAGE_REGION
        self._access_key = access_key or (
            settings.STORAGE_ACCESS_KEY.get_secret_value() if settings.STORAGE_ACCESS_KEY else None
        )
        self._secret_key = secret_key or (
            settings.STORAGE_SECRET_KEY.get_secret_value() if settings.STORAGE_SECRET_KEY else None
        )
        self._force_path_style = (
            force_path_style if force_path_style is not None else settings.STORAGE_FORCE_PATH_STYLE
        )

    @property
    def name(self) -> str:
        return "s3"

    @property
    def is_configured(self) -> bool:
        return bool(self._bucket_name and self._access_key and self._secret_key)

    def _get_client(self) -> Any:
        """Initialize boto3 client configured with Neon forcePathStyle path-addressing."""
        import boto3

        config_kwargs: dict[str, Any] = {}
        if self._force_path_style:
            config_kwargs["s3"] = {"addressing_style": "path"}

        return boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region_name,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            config=Config(**config_kwargs) if config_kwargs else None,
        )

    async def store_object(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Store bytes in private S3 bucket."""
        if not self.is_configured:
            raise RuntimeError(
                "S3/Neon Object Storage is not configured. Provide STORAGE_BUCKET_NAME, "
                "STORAGE_ACCESS_KEY, and STORAGE_SECRET_KEY."
            )

        client = self._get_client()
        client.put_object(
            Bucket=self._bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    async def retrieve_object(self, key: str) -> bytes:
        """Fetch bytes from private S3 bucket."""
        if not self.is_configured:
            raise RuntimeError("S3/Neon Object Storage is not configured.")

        client = self._get_client()
        resp = client.get_object(Bucket=self._bucket_name, Key=key)
        return resp["Body"].read()

    async def delete_object(self, key: str) -> bool:
        """Delete object from private S3 bucket."""
        if not self.is_configured:
            return False

        try:
            client = self._get_client()
            client.delete_object(Bucket=self._bucket_name, Key=key)
            return True
        except Exception as exc:
            logger.warning("Error deleting S3 object '%s': %s", key, exc)
            return False

    def generate_signed_url(
        self,
        key: str,
        expires_in_seconds: int = 300,
    ) -> str:
        """Generate short-lived pre-signed S3 URL for viewing the asset."""
        if not self.is_configured:
            return ""

        client = self._get_client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_name, "Key": key},
            ExpiresIn=expires_in_seconds,
        )
