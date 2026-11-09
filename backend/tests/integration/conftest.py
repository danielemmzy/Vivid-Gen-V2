"""Integration fixtures for PostgreSQL-backed production tests.

These tests intentionally use the project's migrated PostgreSQL schema and
RLS policies. Each test runs inside an outer transaction; service-level
session.commit() calls use savepoints so the fixture can roll the test data
back when the test ends.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession



def new_id(prefix: str) -> str:
    """Return a unique id that fits the app's VARCHAR(32) identifiers."""
    return f"{prefix[:7]}_{uuid4().hex[:24]}"


@pytest_asyncio.fixture
async def db_session():
    # Import lazily so collection remains possible in environments without
    # the optional PostgreSQL driver; executing these tests requires asyncpg.
    from app.core.database import engine

    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            # Use session-level settings so commits within the service under
            # test do not silently clear the user's RLS context.
            await session.execute(text("SELECT set_config('app.current_user_id', '', false)"))
            await session.execute(text("SELECT set_config('app.is_system_context', 'false', false)"))
            yield session
        finally:
            try:
                await session.rollback()
                await session.close()
            finally:
                if outer_transaction.is_active:
                    await outer_transaction.rollback()
                # set_config(..., false) survives rollback, so explicitly
                # clear session state before returning the pooled connection.
                try:
                    reset_tx = await connection.begin()
                    await connection.execute(text("SELECT set_config('app.current_user_id', '', false)"))
                    await connection.execute(text("SELECT set_config('app.is_system_context', 'false', false)"))
                    await reset_tx.commit()
                except Exception:
                    await connection.rollback()


@pytest.fixture
def as_user():
    async def _as_user(session: AsyncSession, user_id: str) -> None:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, false)"),
            {"uid": user_id},
        )
        await session.execute(text("SELECT set_config('app.is_system_context', 'false', false)"))

    return _as_user
