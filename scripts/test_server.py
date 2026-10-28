"""Standalone test server runner for local API contract verification."""

import asyncio
import os
import sys

# Set test environment and SQLite database file
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./local_data/test_auth.db"
os.environ["ALLOW_DEV_AUTH_BYPASS"] = "false"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.db.base import Base
from app.db.session import get_engine
import uvicorn


async def init_db():
    os.makedirs("./local_data", exist_ok=True)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(init_db())
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
