"""Tests for configuration, environment validation, and security switches."""

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import EnvironmentType, Settings


def test_default_settings():
    """Verify default development settings initialization."""
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
    )
    assert settings.PROJECT_NAME == "ToneTrace AI API"
    assert settings.VERSION == "0.1.0"
    assert settings.ALLOW_DEV_AUTH_BYPASS is False
    assert settings.UPLOAD_MAX_FILE_SIZE_BYTES == 10 * 1024 * 1024
    assert "image/jpeg" in settings.UPLOAD_ALLOWED_MIME_TYPES


def test_production_rejects_dev_auth_bypass():
    """Verify production strictly forbids development auth bypass."""
    with pytest.raises(ValidationError, match="ALLOW_DEV_AUTH_BYPASS cannot be enabled"):
        Settings(
            ENVIRONMENT=EnvironmentType.PRODUCTION,
            ALLOW_DEV_AUTH_BYPASS=True,
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        )


def test_staging_rejects_dev_auth_bypass():
    """Verify staging also strictly forbids development auth bypass."""
    with pytest.raises(ValidationError, match="ALLOW_DEV_AUTH_BYPASS cannot be enabled"):
        Settings(
            ENVIRONMENT=EnvironmentType.STAGING,
            ALLOW_DEV_AUTH_BYPASS=True,
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        )


def test_development_allows_dev_auth_bypass():
    """Verify development permits dev auth bypass if intentionally enabled."""
    settings = Settings(
        ENVIRONMENT=EnvironmentType.DEVELOPMENT,
        ALLOW_DEV_AUTH_BYPASS=True,
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
    )
    assert settings.ALLOW_DEV_AUTH_BYPASS is True


def test_production_rejects_wildcard_cors():
    """Verify production strictly forbids wildcard '*' in CORS origins."""
    with pytest.raises(ValidationError, match="Wildcard '\\*' in ALLOWED_CORS_ORIGINS"):
        Settings(
            ENVIRONMENT=EnvironmentType.PRODUCTION,
            ALLOWED_CORS_ORIGINS=["*"],
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
            AUTH_JWT_SECRET="super-secure-production-jwt-secret-key-32chars!",
        )


def test_production_rejects_weak_or_dev_jwt_secret():
    """Verify production rejects default/insecure AUTH_JWT_SECRET."""
    with pytest.raises(ValidationError, match="CRITICAL SECURITY VIOLATION"):
        Settings(
            ENVIRONMENT=EnvironmentType.PRODUCTION,
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
            AUTH_JWT_SECRET="short",
        )

    with pytest.raises(ValidationError, match="CRITICAL SECURITY VIOLATION"):
        Settings(
            ENVIRONMENT=EnvironmentType.PRODUCTION,
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
            AUTH_JWT_SECRET="tonetrace-dev-insecure-jwt-secret-do-not-use-in-production-1234567890",
        )


def test_cors_origin_parsing():
    """Verify comma-separated string parsing for CORS origins."""
    settings = Settings(
        ALLOWED_CORS_ORIGINS="http://localhost:3000, https://tonetrace.app",
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
    )
    assert settings.ALLOWED_CORS_ORIGINS == [
        "http://localhost:3000",
        "https://tonetrace.app",
    ]


def test_upload_max_size_validation():
    """Verify upload size limits enforce min and max bounds."""
    # Under minimum (1KB)
    with pytest.raises(ValidationError, match="UPLOAD_MAX_FILE_SIZE_BYTES"):
        Settings(
            UPLOAD_MAX_FILE_SIZE_BYTES=500,
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        )

    # Over maximum (50MB)
    with pytest.raises(ValidationError, match="UPLOAD_MAX_FILE_SIZE_BYTES"):
        Settings(
            UPLOAD_MAX_FILE_SIZE_BYTES=60 * 1024 * 1024,
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        )


def test_upload_mime_types_validation():
    """Verify upload MIME types must be image types."""
    # Disallow executable or non-image MIME types
    with pytest.raises(ValidationError, match="Unsupported MIME type"):
        Settings(
            UPLOAD_ALLOWED_MIME_TYPES=["application/pdf", "text/html"],
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        )

    # Disallow empty list
    with pytest.raises(
        ValidationError, match="UPLOAD_ALLOWED_MIME_TYPES must contain at least one"
    ):
        Settings(
            UPLOAD_ALLOWED_MIME_TYPES=[],
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
        )


def test_secrets_masked_in_repr():
    """Verify SecretStr prevents printing raw credentials in string or repr outputs."""
    raw_secret = "super-secret-neon-password-12345"
    settings = Settings(
        GEMINI_API_KEY=SecretStr(raw_secret),
        CLERK_SECRET_KEY=SecretStr(raw_secret),
        DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
    )
    repr_output = repr(settings)
    assert raw_secret not in repr_output
    assert "**********" in repr_output
