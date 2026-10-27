"""Object storage providers package."""

from app.core.config import get_settings
from app.providers.storage.base import BaseStorageProvider
from app.providers.storage.local import LocalStorageProvider
from app.providers.storage.s3 import S3StorageProvider


def get_storage_provider() -> BaseStorageProvider:
    """Factory returning configured storage provider."""
    settings = get_settings()
    if settings.STORAGE_PROVIDER == "s3":
        return S3StorageProvider()
    return LocalStorageProvider()


__all__ = [
    "BaseStorageProvider",
    "LocalStorageProvider",
    "S3StorageProvider",
    "get_storage_provider",
]
