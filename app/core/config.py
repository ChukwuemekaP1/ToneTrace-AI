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
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
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
    ELASTICSEARCH_FALLBACK_TO_DB: bool = True

    # --------------------------------------------------------------------------
    # 5. Multimodal AI Guidance (Google Gemini)
    # --------------------------------------------------------------------------
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_TIMEOUT_SECONDS: float = 20.0
    GEMINI_MAX_RETRIES: int = 2
    GEMINI_MAX_CONTEXT_CHARS: int = 16000
    AI_RATE_LIMIT_PER_MINUTE: int = 10

    # --------------------------------------------------------------------------
    # 6. OCR (Ingredient & Product Scanning)
    # --------------------------------------------------------------------------
    OCR_PROVIDER: Literal["gemini", "ocr_space", "tesseract", "mock"] = "mock"
    OCR_API_KEY: SecretStr | None = None
    OCR_BASE_URL: str = "https://api.ocr.space/parse/image"
    TESSERACT_CMD_PATH: str | None = None

    # --------------------------------------------------------------------------
    # 7. External Product Catalog Data (Open Beauty Facts & Channel3)
    # --------------------------------------------------------------------------
    PRODUCT_DATA_API_KEY: SecretStr | None = None
    PRODUCT_DATA_API_BASE_URL: str | None = None
    OPEN_BEAUTY_FACTS_BASE_URL: str = "https://world.openbeautyfacts.org/api/v2"
    OPEN_BEAUTY_FACTS_USER_AGENT: str = "ToneTraceAI/0.1.0 (contact: admin@tonetrace.app)"
    CHANNEL3_API_KEY: SecretStr | None = None
    CHANNEL3_BASE_URL: str = "https://api.trychannel3.com"

    # --------------------------------------------------------------------------
    # 7b. Scientific Evidence & Regulatory Sources (PubMed & EC CosIng)
    # --------------------------------------------------------------------------
    PUBMED_BASE_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    PUBMED_API_KEY: SecretStr | None = None
    PUBMED_TOOL_NAME: str = "tonetrace_ai"
    PUBMED_CONTACT_EMAIL: str = "dev@tonetrace.ai"
    COSING_API_URL: str = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
    COSING_API_KEY: SecretStr = SecretStr("285a77fd-1257-4271-8507-f0c6b2961203")
    EVIDENCE_CACHE_TTL_HOURS: int = 168

    # --------------------------------------------------------------------------
    # 8. Skin Analysis Engine (Perfect Corp / YouCam S2S API)
    # --------------------------------------------------------------------------
    SKIN_ANALYSIS_PROVIDER: Literal["youcam", "mock"] = "mock"
    SKIN_ANALYSIS_API_KEY: SecretStr | None = None
    SKIN_ANALYSIS_SECRET_KEY: SecretStr | None = None
    SKIN_ANALYSIS_BASE_URL: str = "https://yce-api-01.makeupar.com"
    SKIN_ANALYSIS_ENDPOINT_URL: str | None = None
    SKIN_ANALYSIS_TIMEOUT_SECONDS: float = 20.0
    SKIN_ANALYSIS_RETENTION_DAYS: int = 90

    # --------------------------------------------------------------------------
    # 9. Object Storage & Image Retention Policy (Neon Bucket / S3 / PostgreSQL)
    # --------------------------------------------------------------------------
    # Supports Neon S3-compatible Object Storage ('s3'), PostgreSQL BYTEA ('postgres'), or 'local'.
    STORAGE_PROVIDER: Literal["s3", "postgres", "local"] = "postgres"
    STORAGE_LOCAL_DIR: str = "local_data/storage"
    STORAGE_SIGNING_SECRET: SecretStr = SecretStr(
        "tonetrace-storage-signing-secret-change-in-prod-12345"
    )
    STORAGE_BUCKET_NAME: str = "assets"
    STORAGE_ENDPOINT_URL: str | None = None
    STORAGE_REGION: str = "us-east-1"
    STORAGE_ACCESS_KEY: SecretStr | None = None
    STORAGE_SECRET_KEY: SecretStr | None = None
    STORAGE_FORCE_PATH_STYLE: bool = True  # Mandatory for Neon Object Storage (forcePathStyle)
    OCR_IMAGE_RETENTION_POLICY: Literal["delete_after_ocr", "retain"] = "retain"
    OCR_IMAGE_RETENTION_DAYS: int = 30

    # --------------------------------------------------------------------------
    # 10. Upload Constraints & Security Limits
    # --------------------------------------------------------------------------
    UPLOAD_MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB default for PostgreSQL BYTEA MVP
    UPLOAD_MAX_IMAGE_DIMENSION: int = 4096
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
            if self.DEBUG:
                raise ValueError(
                    "CRITICAL SECURITY VIOLATION: DEBUG mode cannot be enabled in production."
                )
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

    def audit_production_readiness(self) -> list[str]:
        """Return a list of deployment readiness warnings or blockers for production."""
        findings: list[str] = []
        raw_storage_secret = self.STORAGE_SIGNING_SECRET.get_secret_value().strip()
        if "change-in-prod" in raw_storage_secret or len(raw_storage_secret) < 32:
            findings.append(
                "STORAGE_SIGNING_SECRET is using the default development value or is < 32 chars."
            )
        if not self.AUTH_RATE_LIMIT_ENABLED:
            findings.append("AUTH_RATE_LIMIT_ENABLED is False; rate limiting must be enabled.")
        if self.ELASTICSEARCH_ENABLED and self.ELASTICSEARCH_URL.startswith("http://"):
            findings.append(
                "ELASTICSEARCH_URL uses unencrypted 'http://'; production requires 'https://'."
            )
        if self.OCR_PROVIDER == "mock":
            findings.append("OCR_PROVIDER is set to 'mock'; configure a verified OCR provider.")
        if self.SKIN_ANALYSIS_PROVIDER == "mock":
            findings.append(
                "SKIN_ANALYSIS_PROVIDER is set to 'mock'; configure verified YouCam credentials."
            )
        return findings

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
