"""Database engine, session management, and health checking.

Configured for SQLAlchemy 2.x async engine with Psycopg 3 for Neon PostgreSQL.
"""

import asyncio
import logging
import sys
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

# Configure Windows selector event loop policy for Psycopg 3 async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger(__name__)

# Global engine and sessionmaker singletons
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Initialize or return the cached async SQLAlchemy engine.

    Configured with resilient connection-pool settings for Neon PostgreSQL:
    - pool_pre_ping: validates connections prior to checkout (vital for serverless scale-to-zero)
    - pool_recycle: proactively recycles sockets before proxy idle dropouts
    - pool_size & max_overflow: compact sizing tailored to serverless transaction pooling
    """
    global _engine
    if _engine is None:
        if settings is None:
            settings = get_settings()

        db_url = settings.get_async_database_url()

        # Engine arguments customized by environment
        engine_kwargs: dict = {
            "echo": settings.DATABASE_ECHO,
            "future": True,
        }

        # SQLite does not support pool_size or max_overflow
        if "sqlite" not in db_url:
            engine_kwargs.update(
                {
                    "pool_size": settings.DATABASE_POOL_SIZE,
                    "max_overflow": settings.DATABASE_MAX_OVERFLOW,
                    "pool_timeout": settings.DATABASE_POOL_TIMEOUT_SECONDS,
                    "pool_recycle": settings.DATABASE_POOL_RECYCLE_SECONDS,
                    "pool_pre_ping": True,  # Critical for Neon serverless idle disconnects
                }
            )

        _engine = create_async_engine(db_url, **engine_kwargs)
        target_db = "sqlite" if "sqlite" in db_url else "PostgreSQL"
        logger.info(f"Initialized SQLAlchemy async engine (database target: {target_db})")
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Initialize or return the cached async sessionmaker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine(settings)
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session with automatic cleanup."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def transactional_session(
    settings: Settings | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager providing explicit transaction boundary with auto-commit and rollback."""
    factory = get_session_factory(settings)
    async with factory() as session:
        try:
            async with session.begin():
                yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db_engine() -> None:
    """Gracefully dispose the database connection pool during application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine connections successfully disposed.")


async def check_db_health(settings: Settings | None = None) -> tuple[bool, float, str | None]:
    """Execute a lightweight probe ('SELECT 1') to assess database readiness.

    Returns:
        (is_healthy, latency_ms, error_message)
    """
    if settings is None:
        settings = get_settings()

    if not settings.DATABASE_URL and not settings.is_testing:
        return False, 0.0, "DATABASE_URL is not configured."

    start_time = time.perf_counter()
    try:
        # Enforce pool timeout on probe to prevent blocking readiness checks indefinitely
        probe_timeout = max(settings.DATABASE_POOL_TIMEOUT_SECONDS, 5.0)
        async with asyncio.timeout(probe_timeout):
            engine = get_engine(settings)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start_time) * 1000.0
        return True, round(latency, 2), None
    except Exception as exc:
        latency = (time.perf_counter() - start_time) * 1000.0
        error_msg = f"Database probe failed: {type(exc).__name__}: {exc}"
        logger.warning(f"Database health check failed ({error_msg})", exc_info=True)
        return False, round(latency, 2), error_msg
