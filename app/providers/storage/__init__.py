"""Private storage providers package (Neon S3 Object Storage, PostgreSQL BYTEA, and Local)."""

from app.core.config import get_settings
from app.providers.storage.base import BaseStorageProvider
from app.providers.storage.local import LocalStorageProvider
from app.providers.storage.postgres import PostgresStorageProvider
from app.providers.storage.s3 import S3StorageProvider


def get_storage_provider() -> BaseStorageProvider:
    """Factory returning configured storage engine ('s3', 'postgres', or 'local')."""
    settings = get_settings()
    if settings.STORAGE_PROVIDER == "s3":
        return S3StorageProvider()
    if settings.STORAGE_PROVIDER == "local":
        return LocalStorageProvider()
    return PostgresStorageProvider()


__all__ = [
    "BaseStorageProvider",
    "LocalStorageProvider",
    "PostgresStorageProvider",
    "S3StorageProvider",
    "get_storage_provider",
]
