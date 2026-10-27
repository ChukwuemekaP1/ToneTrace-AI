"""Private S3 / Cloudflare R2 compatible object storage provider.

Generates pre-signed S3 URLs without ever exposing public buckets.
"""

import logging

from app.core.config import get_settings
from app.providers.storage.base import BaseStorageProvider

logger = logging.getLogger(__name__)


class S3StorageProvider(BaseStorageProvider):
    """S3-compatible private object storage provider (AWS S3, Cloudflare R2, MinIO)."""

    def __init__(
        self,
        bucket_name: str | None = None,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
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

    @property
    def name(self) -> str:
        return "s3"

    @property
    def is_configured(self) -> bool:
        return bool(self._bucket_name and self._access_key and self._secret_key)

    async def store_object(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Store bytes in private S3 bucket."""
        if not self.is_configured:
            raise RuntimeError("S3 storage is not configured. Provide bucket and credentials.")
        # When boto3 is installed in production
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region_name,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )
        s3.put_object(
            Bucket=self._bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    async def retrieve_object(self, key: str) -> bytes:
        """Fetch bytes from private S3 bucket."""
        if not self.is_configured:
            raise RuntimeError("S3 storage is not configured.")
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region_name,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )
        resp = s3.get_object(Bucket=self._bucket_name, Key=key)
        return resp["Body"].read()

    async def delete_object(self, key: str) -> bool:
        """Delete object from private S3 bucket."""
        if not self.is_configured:
            return False
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region_name,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )
        s3.delete_object(Bucket=self._bucket_name, Key=key)
        return True

    def generate_signed_url(
        self,
        key: str,
        expires_in_seconds: int = 300,
    ) -> str:
        """Generate short-lived pre-signed S3 URL."""
        if not self.is_configured:
            return ""
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region_name,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_name, "Key": key},
            ExpiresIn=expires_in_seconds,
        )
