"""Tests for database layer, session lifecycle, transaction rollback, and migration discovery.

NOTE: Tests in this file execute against an isolated async SQLite engine or mocked
connections to guarantee fast, deterministic local test execution without external
network dependencies. As documented in project architecture standards, passing tests
against an isolated test database verify ORM mechanics and transactional guarantees,
but DO NOT substitute for proving live end-to-end Neon PostgreSQL connectivity.
"""

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.db.models import SystemAuditLog
from app.db.session import check_db_health, transactional_session


@pytest.fixture
async def isolated_db_engine():
    """Create a completely isolated in-memory SQLite engine for testing ORM semantics."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def isolated_session_factory(isolated_db_engine):
    """Sessionmaker bound to the isolated in-memory test engine."""
    return async_sessionmaker(
        bind=isolated_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def test_normalize_postgres_url():
    """Verify PostgreSQL URL normalization to Psycopg 3 driver and TLS enforcement."""
    # 1. postgres:// normalization
    raw_url = "postgres://user:pass@ep-sample.us-east-2.aws.neon.tech/neondb"
    normalized = Settings.normalize_postgres_url(raw_url, enforce_tls=True)
    assert normalized.startswith("postgresql+psycopg://")
    assert "sslmode=require" in normalized

    # 2. postgresql:// normalization
    raw_url2 = "postgresql://user:pass@ep-sample.us-east-2.aws.neon.tech/neondb?sslmode=require"
    normalized2 = Settings.normalize_postgres_url(raw_url2, enforce_tls=True)
    assert normalized2.startswith("postgresql+psycopg://")
    assert "sslmode=require" in normalized2

    # 3. Reject insecure sslmode=disable
    insecure_url = "postgresql://user:pass@ep-sample.us-east-2.aws.neon.tech/neondb?sslmode=disable"
    with pytest.raises(ValueError, match="TLS encryption is mandatory for Neon"):
        Settings.normalize_postgres_url(insecure_url, enforce_tls=True)


def test_direct_vs_runtime_url_separation():
    """Verify runtime uses DATABASE_URL (pooler) while migrations use DIRECT_URL."""
    pooled_url = (
        "postgresql://user:pass@ep-sample-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    )
    direct_url = "postgresql://user:pass@ep-sample.us-east-2.aws.neon.tech/neondb?sslmode=require"

    settings = Settings(
        DATABASE_URL=pooled_url,
        DIRECT_URL=direct_url,
    )

    runtime_url = settings.get_async_database_url()
    migration_url = settings.get_direct_database_url()

    assert "-pooler" in runtime_url
    assert "-pooler" not in migration_url
    assert runtime_url.startswith("postgresql+psycopg://")
    assert migration_url.startswith("postgresql+psycopg://")


@pytest.mark.asyncio
async def test_session_lifecycle(isolated_session_factory, monkeypatch):
    """Verify get_db_session yields an active session and closes upon generator completion."""
    from app.db.session import get_db_session

    monkeypatch.setattr("app.db.session.get_session_factory", lambda *_: isolated_session_factory)

    gen = get_db_session()
    session = await anext(gen)
    result = await session.execute(text("SELECT 1"))
    assert result.scalar() == 1

    with pytest.raises(StopAsyncIteration):
        await anext(gen)


@pytest.mark.asyncio
async def test_transaction_rollback_on_failure(isolated_db_engine, monkeypatch):
    """Verify that an exception inside transactional_session rolls back uncommitted writes."""
    test_settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )

    # Point session factory to our pre-migrated isolated engine
    test_factory = async_sessionmaker(
        bind=isolated_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr("app.db.session.get_session_factory", lambda *_: test_factory)

    test_event_name = f"EVENT_{uuid.uuid4().hex[:8]}"

    # Attempt an insert and raise an exception
    with pytest.raises(RuntimeError, match="Simulated mid-transaction failure"):
        async with transactional_session(test_settings) as session:
            log_entry = SystemAuditLog(
                event_name=test_event_name,
                source="test_suite",
                details="This entry should be rolled back",
            )
            session.add(log_entry)
            await session.flush()
            raise RuntimeError("Simulated mid-transaction failure")

    # Verify record was rolled back and is not in the database
    async with test_factory() as verify_session:
        stmt = select(SystemAuditLog).where(SystemAuditLog.event_name == test_event_name)
        result = await verify_session.execute(stmt)
        record = result.scalars().first()
        assert record is None


@pytest.mark.asyncio
async def test_transaction_commit_on_success(isolated_db_engine, monkeypatch):
    """Verify that successful transactional_session cleanly commits changes."""
    test_settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )

    test_factory = async_sessionmaker(
        bind=isolated_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr("app.db.session.get_session_factory", lambda *_: test_factory)

    test_event_name = f"EVENT_{uuid.uuid4().hex[:8]}"

    async with transactional_session(test_settings) as session:
        log_entry = SystemAuditLog(
            event_name=test_event_name,
            source="test_suite",
            details="Successfully committed event",
        )
        session.add(log_entry)

    # Verify record is persisted
    async with test_factory() as verify_session:
        stmt = select(SystemAuditLog).where(SystemAuditLog.event_name == test_event_name)
        result = await verify_session.execute(stmt)
        record = result.scalars().first()
        assert record is not None
        assert record.event_name == test_event_name
        assert record.source == "test_suite"


@pytest.mark.asyncio
async def test_database_health_check_failure():
    """Verify check_db_health returns unhealthy state when connection is unreachable."""
    bad_settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql://invalid_user:bad_pass@127.0.0.1:1/dummy?sslmode=require",
    )
    is_healthy, latency, error_msg = await check_db_health(bad_settings)
    assert is_healthy is False
    assert error_msg is not None
    assert "Database probe failed" in error_msg


def test_alembic_migration_discovery():
    """Verify Alembic configuration correctly locates migration revisions."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    revisions = list(script.walk_revisions())
    assert len(revisions) >= 1
    assert any("create system audit log table" in (rev.doc or "").lower() for rev in revisions)
