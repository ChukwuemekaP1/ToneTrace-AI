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
from app.providers.open_beauty_facts import (
    OpenBeautyFactsAdapter,
    OpenBeautyFactsError,
    OpenBeautyFactsProduct,
    OpenBeautyFactsRateLimitError,
    OpenBeautyFactsUnavailableError,
    ParsedIngredient,
)
from app.providers.search_provider import SearchProvider, get_search_provider

__all__ = [
    "BaseProvider",
    "Channel3Adapter",
    "Channel3AuthenticationError",
    "Channel3Error",
    "Channel3NotConfiguredError",
    "Channel3ProductOffer",
    "Channel3RateLimitError",
    "Channel3UnavailableError",
    "OpenBeautyFactsAdapter",
    "OpenBeautyFactsError",
    "OpenBeautyFactsProduct",
    "OpenBeautyFactsRateLimitError",
    "OpenBeautyFactsUnavailableError",
    "ParsedIngredient",
    "SearchProvider",
    "evaluate_integration_status",
    "get_search_provider",
]
