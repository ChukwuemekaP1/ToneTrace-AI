"""Abstract private object storage provider interface.

Guarantees:
- Never exposes raw or public bucket endpoints.
- Requires authenticated, time-bounded access via signed URLs.
- Never logs image bytes or secrets.
"""

from abc import ABC, abstractmethod


class BaseStorageProvider(ABC):
    """Abstract contract for private object storage engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Storage engine identifier (e.g. 'local', 's3', 'r2')."""
        pass

    @abstractmethod
    async def store_object(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Persist object bytes under key.

        Returns storage key on success.
        """
        pass

    @abstractmethod
    async def retrieve_object(self, key: str) -> bytes:
        """Fetch raw bytes of stored object."""
        pass

    @abstractmethod
    async def delete_object(self, key: str) -> bool:
        """Delete object under key. Returns True if deleted or did not exist."""
        pass

    @abstractmethod
    def generate_signed_url(
        self,
        key: str,
        expires_in_seconds: int = 300,
    ) -> str:
        """Generate a short-lived authenticated URL for reading the object."""
        pass
