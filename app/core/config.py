"""Application configuration and settings management.

Utilizes Pydantic v2 Settings for strict type validation, environment variable
parsing, and secure handling of credentials using SecretStr.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Any, Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentType(StrEnum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class IntegrationState(StrEnum):
    """Status states for safe integration reporting."""

    CONFIGURED = "configured"
    UNCONFIGURED = "unconfigured"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"


class Settings(BaseSettings):
    """Master application settings schema.

    Secrets use SecretStr to guarantee they are never logged or serialized
    in plain text representations.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --------------------------------------------------------------------------
    # 1. Core Application
    # --------------------------------------------------------------------------
    PROJECT_NAME: str = "ToneTrace AI API"
    VERSION: str = "0.1.0"
    ENVIRONMENT: EnvironmentType = EnvironmentType.DEVELOPMENT
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    ALLOWED_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # --------------------------------------------------------------------------
    # 2. Security & Auth Controls (First-Party Authentication)
    # --------------------------------------------------------------------------
    ALLOW_DEV_AUTH_BYPASS: bool = False

    # First-Party JWT & Session Authentication
    AUTH_JWT_SECRET: SecretStr = SecretStr(
        "tonetrace-dev-insecure-jwt-secret-do-not-use-in-production-1234567890"
    )
    AUTH_JWT_ISSUER: str = "tonetrace-auth"
    AUTH_JWT_AUDIENCE: str = "tonetrace-api"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 30
    PASSWORD_MIN_LENGTH: int = 8
    AUTH_RATE_LIMIT_ENABLED: bool = True
    AUTH_RATE_LIMIT_PER_MINUTE: int = 20

    # Clerk Integration (Optional external IDP placeholder - not used in Phase 2)
    CLERK_SECRET_KEY: SecretStr | None = None
    CLERK_PUBLISHABLE_KEY: str | None = None
    CLERK_ISSUER: str | None = None
    CLERK_JWKS_URL: str | None = None

    # --------------------------------------------------------------------------
    # 3. Database (Neon Serverless PostgreSQL)
    # --------------------------------------------------------------------------
    DATABASE_URL: str | None = None
    DIRECT_URL: str | None = None
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 5
    DATABASE_POOL_TIMEOUT_SECONDS: float = 10.0
    DATABASE_POOL_RECYCLE_SECONDS: int = 300
    DATABASE_ECHO: bool = False

    # --------------------------------------------------------------------------
    # 4. Search & Indexing (Elasticsearch)
    # --------------------------------------------------------------------------
    ELASTICSEARCH_ENABLED: bool = False
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_USERNAME: str | None = None
    ELASTICSEARCH_PASSWORD: SecretStr | None = None
    ELASTICSEARCH_API_KEY: SecretStr | None = None
    ELASTICSEARCH_INDEX_PREFIX: str = "tonetrace_"
    ELASTICSEARCH_REQUEST_TIMEOUT_SECONDS: float = 10.0
    ELASTICSEARCH_VERIFY_CERTS: bool = True
    ELASTICSEARCH_FALLBACK_TO_DB: bool = False

    # --------------------------------------------------------------------------
    # 5. Multimodal AI Guidance (Google Gemini)
    # --------------------------------------------------------------------------
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-1.5-pro"

    # --------------------------------------------------------------------------
    # 6. OCR (Ingredient & Product Scanning)
    # --------------------------------------------------------------------------
    OCR_PROVIDER: str = "google_cloud_vision"
    OCR_API_KEY: SecretStr | None = None
    OCR_ENDPOINT_URL: str | None = None

    # --------------------------------------------------------------------------
    # 7. External Product Catalog Data (Open Beauty Facts & Channel3)
    # --------------------------------------------------------------------------
    PRODUCT_DATA_API_KEY: SecretStr | None = None
    PRODUCT_DATA_API_BASE_URL: str | None = None
    OPEN_BEAUTY_FACTS_BASE_URL: str = "https://world.openbeautyfacts.org/api/v2"
    OPEN_BEAUTY_FACTS_USER_AGENT: str = "ToneTraceAI/0.1.0 (contact: admin@tonetrace.app)"
    CHANNEL3_API_KEY: SecretStr | None = None
    CHANNEL3_BASE_URL: str = "https://api.trychannel3.com/v1"

    # --------------------------------------------------------------------------
    # 8. Skin Analysis Engine
    # --------------------------------------------------------------------------
    SKIN_ANALYSIS_API_KEY: SecretStr | None = None
    SKIN_ANALYSIS_ENDPOINT_URL: str | None = None

    # --------------------------------------------------------------------------
    # 9. Cloud Object Storage
    # --------------------------------------------------------------------------
    STORAGE_PROVIDER: Literal["s3", "gcs", "local"] = "s3"
    STORAGE_BUCKET_NAME: str | None = None
    STORAGE_REGION: str = "us-east-1"
    STORAGE_ENDPOINT_URL: str | None = None
    STORAGE_ACCESS_KEY: SecretStr | None = None
    STORAGE_SECRET_KEY: SecretStr | None = None

    # --------------------------------------------------------------------------
    # 10. Upload Constraints & Security Limits
    # --------------------------------------------------------------------------
    UPLOAD_MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB default
    UPLOAD_ALLOWED_MIME_TYPES: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]

    # --------------------------------------------------------------------------
    # Validators
    # --------------------------------------------------------------------------
    @field_validator("UPLOAD_MAX_FILE_SIZE_BYTES")
    @classmethod
    def validate_max_upload_size(cls, v: int) -> int:
        """Ensure upload size limits are sane (between 1KB and 50MB)."""
        min_size = 1024  # 1 KB
        max_size = 50 * 1024 * 1024  # 50 MB
        if v < min_size or v > max_size:
            raise ValueError(
                f"UPLOAD_MAX_FILE_SIZE_BYTES must be between {min_size} bytes (1KB) "
                f"and {max_size} bytes (50MB). Provided: {v}"
            )
        return v

    @field_validator("UPLOAD_ALLOWED_MIME_TYPES")
    @classmethod
    def validate_allowed_mime_types(cls, v: list[str]) -> list[str]:
        """Ensure allowed MIME types list is not empty and restricted to supported image formats."""
        if not v:
            raise ValueError("UPLOAD_ALLOWED_MIME_TYPES must contain at least one MIME type.")
        valid_mime_prefixes = ("image/",)
        for mime in v:
            if not any(mime.startswith(prefix) for prefix in valid_mime_prefixes):
                raise ValueError(
                    f"Unsupported MIME type '{mime}'. Only image formats are permitted."
                )
        return v

    @field_validator("ALLOWED_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins if provided as comma-separated string or list."""
        if isinstance(v, str):
            if v.strip().startswith("[") and v.strip().endswith("]"):
                # Handled by pydantic JSON parsing
                return [s.strip().strip("\"'") for s in v.strip()[1:-1].split(",") if s.strip()]
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return [str(s).strip() for s in v if str(s).strip()]
        return v

    @model_validator(mode="after")
    def validate_production_security_constraints(self) -> "Settings":
        """Strictly enforce security policies in production and staging environments."""
        is_production = self.ENVIRONMENT == EnvironmentType.PRODUCTION
        is_staging_or_prod = self.ENVIRONMENT in (
            EnvironmentType.PRODUCTION,
            EnvironmentType.STAGING,
        )

        # 1. Dev Auth Bypass must never be active outside development/test
        if is_staging_or_prod and self.ALLOW_DEV_AUTH_BYPASS:
            raise ValueError(
                f"CRITICAL SECURITY VIOLATION: ALLOW_DEV_AUTH_BYPASS cannot be enabled "
                f"in environment '{self.ENVIRONMENT.value}'."
            )

        # 2. Enforce secure JWT Secret in production/staging
        if is_staging_or_prod:
            raw_jwt_secret = self.AUTH_JWT_SECRET.get_secret_value().strip()
            if (
                not raw_jwt_secret
                or "insecure-jwt-secret" in raw_jwt_secret
                or len(raw_jwt_secret) < 32
            ):
                raise ValueError(
                    f"CRITICAL SECURITY VIOLATION: Strong AUTH_JWT_SECRET (>= 32 characters) "
                    f"is required in environment '{self.ENVIRONMENT.value}'."
                )

        # 3. CORS Wildcard check
        if is_production:
            if "*" in self.ALLOWED_CORS_ORIGINS:
                raise ValueError(
                    "CRITICAL SECURITY VIOLATION: Wildcard '*' in ALLOWED_CORS_ORIGINS is "
                    "strictly prohibited in production."
                )
            if not self.ALLOWED_CORS_ORIGINS:
                raise ValueError(
                    "ALLOWED_CORS_ORIGINS must contain explicit origin URLs in production."
                )

        return self

    @property
    def is_production(self) -> bool:
        """Convenience property for production check."""
        return self.ENVIRONMENT == EnvironmentType.PRODUCTION

    @property
    def is_testing(self) -> bool:
        """Convenience property for test environment check."""
        return self.ENVIRONMENT == EnvironmentType.TEST

    @staticmethod
    def normalize_postgres_url(url: str, enforce_tls: bool = True) -> str:
        """Normalize PostgreSQL connection strings to SQLAlchemy 2.x Psycopg 3 format.

        Supports postgres://, postgresql://, postgresql+psycopg://, and enforces TLS.
        """
        normalized = url.strip()

        # Normalize driver prefix
        if normalized.startswith("postgres://"):
            normalized = normalized.replace("postgres://", "postgresql+psycopg://", 1)
        elif normalized.startswith("postgresql://") and not normalized.startswith(
            "postgresql+psycopg://"
        ):
            normalized = normalized.replace("postgresql://", "postgresql+psycopg://", 1)
        elif normalized.startswith("postgresql+asyncpg://"):
            normalized = normalized.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)

        # Skip TLS checks on SQLite or local test hosts
        if "sqlite" in normalized or "localhost" in normalized or "127.0.0.1" in normalized:
            return normalized

        # Enforce TLS for remote connections (especially Neon)
        if enforce_tls:
            url_lower = normalized.lower()
            if "sslmode=disable" in url_lower or "sslmode=allow" in url_lower:
                raise ValueError(
                    "Insecure connection rejected: TLS encryption is mandatory for Neon. "
                    "Please set 'sslmode=require' in your connection string."
                )
            if "sslmode=" not in url_lower:
                delimiter = "&" if "?" in normalized else "?"
                normalized = f"{normalized}{delimiter}sslmode=require"

        return normalized

    def get_async_database_url(self) -> str:
        """Get the SQLAlchemy async driver formatted database URL for application runtime."""
        if not self.DATABASE_URL:
            if self.is_testing:
                # Isolated in-memory SQLite specifically and only for unit tests
                return "sqlite+aiosqlite:///:memory:"
            raise ValueError(
                "DATABASE_URL is not configured. "
                "Please supply a valid Neon PostgreSQL connection string."
            )

        return self.normalize_postgres_url(
            self.DATABASE_URL,
            enforce_tls=not self.is_testing,
        )

    def get_direct_database_url(self) -> str:
        """Get the direct unpooled database URL for Alembic migrations.

        Alembic DDL migrations require direct unpooled connections because
        transaction poolers (e.g. PgBouncer) do not support certain migration operations.
        Falls back to DATABASE_URL if DIRECT_URL is not provided.
        """
        raw_url = self.DIRECT_URL or self.DATABASE_URL
        if not raw_url:
            if self.is_testing:
                return "sqlite+aiosqlite:///:memory:"
            raise ValueError("Neither DIRECT_URL nor DATABASE_URL is configured for migrations.")

        return self.normalize_postgres_url(
            raw_url,
            enforce_tls=not self.is_testing,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton getter for cached application settings."""
    return Settings()
