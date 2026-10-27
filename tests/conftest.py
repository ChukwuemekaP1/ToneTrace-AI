"""Pytest fixtures and configuration for ToneTrace AI test suite."""

import os
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Ensure test environment by default
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["ALLOW_DEV_AUTH_BYPASS"] = "false"
os.environ["OCR_PROVIDER"] = "mock"

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def test_settings() -> Settings:
    """Fixture providing clean test settings."""
    settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+aiosqlite://",
        ALLOW_DEV_AUTH_BYPASS=False,
        ALLOWED_CORS_ORIGINS=["http://localhost:3000"],
        AUTH_JWT_SECRET="test-super-secret-key-at-least-32-chars-long-12345",
        AUTH_JWT_ISSUER="tonetrace-test",
        AUTH_JWT_AUDIENCE="tonetrace-api-test",
        ACCESS_TOKEN_TTL_MINUTES=15,
        REFRESH_TOKEN_TTL_DAYS=7,
        PASSWORD_MIN_LENGTH=8,
        AUTH_RATE_LIMIT_ENABLED=True,
        OCR_PROVIDER="mock",
        STORAGE_PROVIDER="local",
        STORAGE_LOCAL_DIR="./var/test_storage",
    )
    get_settings.cache_clear()
    return settings


@pytest.fixture
async def test_db_engine():
    """Isolated in-memory SQLite database engine with tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an AsyncSession bound to the test SQLite database."""
    session_factory = async_sessionmaker(
        bind=test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def app(test_settings: Settings, test_db_engine) -> FastAPI:
    """FastAPI application instance configured with test settings and database override."""
    app_instance = create_app(test_settings)

    session_factory = async_sessionmaker(
        bind=test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app_instance.dependency_overrides[get_settings] = lambda: test_settings
    app_instance.dependency_overrides[get_db_session] = override_get_db_session
    return app_instance


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP test client bound to the FastAPI ASGI application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
