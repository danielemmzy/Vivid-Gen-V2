"""Fixtures for the integration test suite (Tests 1, 3, 4, 5 from the audit
plan). These need a REAL Postgres with the app's migrations — including
0002_row_level_security.py — actually applied, and a real Redis for the
job queue. That's the whole point: Tests 1-5 are specifically about
proving RLS, credit locking, and reconciliation behave correctly at the
database level, which a mocked session can't tell you.

Run them with:
    docker compose -f docker-compose.test.yml up -d
    alembic upgrade head          # against the test DB — see TEST_DATABASE_URL below
    pytest tests/integration -m integration

If TEST_DATABASE_URL isn't set (or the DB isn't reachable), every test in
this package is skipped rather than erroring — so `pytest` with no test
infra running still passes cleanly and only the unit suite runs.
"""
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.integration


def _db_available() -> bool:
    return bool(TEST_DATABASE_URL)


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL not set — skipping integration suite (see conftest.py docstring)")
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async with engine.connect() as conn:
        try:
            await conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"TEST_DATABASE_URL not reachable: {exc}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


async def _set_user_context(session: AsyncSession, user_id: str | None, is_system: bool = False) -> None:
    """Mirrors what core/database.py's get_db()/system_session() do in the
    real app — set the same session-local Postgres variables the RLS
    policies check, scoped with `true` (transaction-local) so it never
    leaks across a pooled connection."""
    if is_system:
        await session.execute(text("SELECT set_config('app.is_system_context', 'true', true)"))
    if user_id:
        await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_id})


@pytest_asyncio.fixture
async def as_user():
    """Usage: `await as_user(session, "user_a")` — call at the start of a
    test body once you have a session, to scope every subsequent query on
    it to that user, exactly like a real authenticated request would."""
    return _set_user_context


@pytest_asyncio.fixture
async def as_system():
    async def _apply(session: AsyncSession):
        await _set_user_context(session, None, is_system=True)
    return _apply


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
