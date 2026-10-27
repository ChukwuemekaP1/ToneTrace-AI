"""Provider interfaces and integration safety audit.

Defines the contract for external service providers and provides safe
status reporting without exposing secrets, credentials, or keys.
"""

import logging
from abc import ABC, abstractmethod

from app.core.config import IntegrationState, Settings
from app.schemas.health import IntegrationItem

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """Abstract base class for all third-party and outbound service providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier."""
        pass

    @abstractmethod
    async def check_health(self) -> tuple[bool, str | None]:
        """Verify external provider connectivity and health.

        Returns:
            (is_healthy, diagnostic_summary)
        """
        pass


def evaluate_integration_status(settings: Settings) -> dict[str, IntegrationItem]:
    """Safely assess the configuration state of all planned integrations.

    Zero-knowledge guarantee:
    Never returns secrets, tokens, URLs with embedded passwords, or sensitive keys.
    Only returns categorical state (configured, unconfigured, disabled, unavailable).
    """
    integrations: dict[str, IntegrationItem] = {}

    # 1. Database (Neon PostgreSQL)
    has_db = bool(settings.DATABASE_URL)
    integrations["database"] = IntegrationItem(
        state=IntegrationState.CONFIGURED if has_db else IntegrationState.UNCONFIGURED,
        provider="Neon Serverless PostgreSQL" if has_db else None,
        description="Primary relational datastore.",
    )

    # 2. First-Party Authentication
    has_auth = bool(
        settings.AUTH_JWT_SECRET and settings.AUTH_JWT_SECRET.get_secret_value().strip()
    )
    integrations["first_party_auth"] = IntegrationItem(
        state=IntegrationState.CONFIGURED if has_auth else IntegrationState.UNCONFIGURED,
        provider="Argon2id + PyJWT",
        description="First-party user authentication and rotating session management.",
    )

    # 3. Elasticsearch
    if not settings.ELASTICSEARCH_ENABLED:
        es_state = IntegrationState.DISABLED
    elif settings.ELASTICSEARCH_URL:
        es_state = IntegrationState.CONFIGURED
    else:
        es_state = IntegrationState.UNCONFIGURED

    integrations["elasticsearch"] = IntegrationItem(
        state=es_state,
        provider="Elasticsearch 8.x / 9.x",
        description="Cosmetic product & ingredient search indexing.",
    )

    # 3. Clerk Authentication
    has_clerk = bool(
        settings.CLERK_SECRET_KEY and settings.CLERK_SECRET_KEY.get_secret_value().strip()
    )
    integrations["clerk_auth"] = IntegrationItem(
        state=IntegrationState.CONFIGURED if has_clerk else IntegrationState.UNCONFIGURED,
        provider="Clerk Identity",
        description="JWT user authentication and session management.",
    )

    # 4. Google Gemini AI
    has_gemini = bool(
        settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.get_secret_value().strip()
    )
    integrations["gemini_ai"] = IntegrationItem(
        state=IntegrationState.CONFIGURED if has_gemini else IntegrationState.UNCONFIGURED,
        provider=f"Google Gemini ({settings.GEMINI_MODEL})",
        description="Multimodal skincare guidance and explanation engine.",
    )

    # 5. OCR Engine
    has_ocr = bool(settings.OCR_API_KEY and settings.OCR_API_KEY.get_secret_value().strip())
    integrations["ocr"] = IntegrationItem(
        state=IntegrationState.CONFIGURED if has_ocr else IntegrationState.UNCONFIGURED,
        provider=settings.OCR_PROVIDER,
        description="Ingredient list optical character recognition.",
    )

    # 6. External Product Catalog Data
    has_product_api = bool(
        settings.PRODUCT_DATA_API_KEY and settings.PRODUCT_DATA_API_KEY.get_secret_value().strip()
    )
    integrations["product_catalog"] = IntegrationItem(
        state=IntegrationState.CONFIGURED if has_product_api else IntegrationState.UNCONFIGURED,
        provider="External Cosmetic Registry API",
        description="Product ingredients and safety verification data.",
    )

    # 7. Skin Analysis Engine
    has_skin_api = bool(
        settings.SKIN_ANALYSIS_API_KEY and settings.SKIN_ANALYSIS_API_KEY.get_secret_value().strip()
    )
    integrations["skin_analysis"] = IntegrationItem(
        state=IntegrationState.CONFIGURED if has_skin_api else IntegrationState.UNCONFIGURED,
        provider="Dermatological Analysis Engine",
        description="Skin metric quantification and visual concern detection.",
    )

    # 8. Cloud Object Storage
    has_storage = bool(settings.STORAGE_BUCKET_NAME)
    integrations["object_storage"] = IntegrationItem(
        state=IntegrationState.CONFIGURED if has_storage else IntegrationState.UNCONFIGURED,
        provider=settings.STORAGE_PROVIDER.upper(),
        description="Facial scan images and processed asset store.",
    )

    # 9. Open Beauty Facts
    integrations["open_beauty_facts"] = IntegrationItem(
        state=IntegrationState.CONFIGURED,
        provider="Open Beauty Facts (ODbL 1.0)",
        description="Open database of cosmetics products and ingredient declarations.",
    )

    # 10. Channel3 Offers & Pricing
    has_channel3 = bool(
        settings.CHANNEL3_API_KEY and settings.CHANNEL3_API_KEY.get_secret_value().strip()
    )
    integrations["channel3"] = IntegrationItem(
        state=IntegrationState.CONFIGURED if has_channel3 else IntegrationState.UNCONFIGURED,
        provider="Channel3 Retail API",
        description="Commercial cosmetic merchant offers, prices, and stock availability.",
    )

    return integrations
