"""Dedicated-database fixtures for recovered production-safety coverage.

Run with TEST_DATABASE_URL pointing at backend/docker-compose.test.yml. This
module deliberately overrides DATABASE_URL before importing app.database so a
test run cannot silently use the development database.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def new_id(prefix: str) -> str:
    return f"{prefix[:7]}_{uuid.uuid4().hex[:24]}"


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is required for recovered integration tests")
    # NullPool keeps asyncpg connections bound to the event loop that created
    # them; pytest-asyncio may use a fresh loop per test on Windows.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def as_system():
    async def _apply(session: AsyncSession):
        await session.execute(text("SELECT set_config('app.is_system_context', 'true', false)"))
        await session.execute(text("SELECT set_config('app.current_user_id', '', false)"))

    return _apply


@pytest.fixture
def as_user():
    async def _apply(session: AsyncSession, user_id: str):
        await session.execute(text("SELECT set_config('app.is_system_context', 'false', false)"))
        await session.execute(text("SELECT set_config('app.current_user_id', :uid, false)"), {"uid": user_id})

    return _apply
