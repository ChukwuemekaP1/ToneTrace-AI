"""Third-party and external service providers package."""

from app.providers.base import BaseProvider, evaluate_integration_status
from app.providers.channel3 import (
    Channel3Adapter,
    Channel3AuthenticationError,
    Channel3Error,
    Channel3NotConfiguredError,
    Channel3ProductOffer,
    Channel3RateLimitError,
    Channel3UnavailableError,
)
from app.providers.ocr import (
    BaseOCRAdapter,
    MockOCRAdapter,
    OCRSpaceAdapter,
    get_ocr_adapter,
)
from app.providers.open_beauty_facts import (
    OpenBeautyFactsAdapter,
    OpenBeautyFactsError,
    OpenBeautyFactsProduct,
    OpenBeautyFactsRateLimitError,
    OpenBeautyFactsUnavailableError,
    ParsedIngredient,
)
from app.providers.search_provider import SearchProvider, get_search_provider
from app.providers.storage import (
    BaseStorageProvider,
    LocalStorageProvider,
    S3StorageProvider,
    get_storage_provider,
)

__all__ = [
    "BaseOCRAdapter",
    "BaseProvider",
    "BaseStorageProvider",
    "Channel3Adapter",
    "Channel3AuthenticationError",
    "Channel3Error",
    "Channel3NotConfiguredError",
    "Channel3ProductOffer",
    "Channel3RateLimitError",
    "Channel3UnavailableError",
    "LocalStorageProvider",
    "MockOCRAdapter",
    "OCRSpaceAdapter",
    "OpenBeautyFactsAdapter",
    "OpenBeautyFactsError",
    "OpenBeautyFactsProduct",
    "OpenBeautyFactsRateLimitError",
    "OpenBeautyFactsUnavailableError",
    "ParsedIngredient",
    "S3StorageProvider",
    "SearchProvider",
    "evaluate_integration_status",
    "get_ocr_adapter",
    "get_search_provider",
    "get_storage_provider",
]
