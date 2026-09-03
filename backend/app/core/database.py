"""Database engine/session factory. This module owns the `core` schema only
— see the architecture plan's Decision 2. Never import Prisma's auth tables
here; the two schemas are migrated independently (Alembic for this one,
Prisma migrate for auth) and are only ever joined in application code via
a user_id string, never a foreign key.

Every session obtained via `get_db()` sets a Postgres session-local
variable, `app.current_user_id`, at the start of the transaction. This is
what the RLS policies in alembic/versions/0002_row_level_security.py key
off of — see that migration's docstring for why this exists at all
(defense in depth: application-level `WHERE user_id = ...` filters remain,
but a future bug that forgets one no longer means the database hands back
another user's rows)."""
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.context.request import get_user_id
from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        user_id = get_user_id()
        if user_id:
            # set_config(..., true) scopes the setting to the current
            # transaction only — it can't leak onto a pooled connection
            # reused by a different request afterwards.
            await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_id})
        yield session


async def get_db_as_system():
    """For code paths that legitimately need to see across users — the
    reconciliation scheduler, admin tooling, webhook handlers keyed by
    provider_request_id rather than user_id. Sets app.is_system_context so
    the RLS policies grant full access; never expose this session to a
    router that only has one user's authorization context."""
    async with SessionLocal() as session:
        await session.execute(text("SELECT set_config('app.is_system_context', 'true', true)"))
        yield session


@asynccontextmanager
async def system_session():
    """Non-FastAPI-dependency version of get_db_as_system, for use in ARQ
    workers and the scheduler loop — neither runs inside a request, so
    there's no dependency injection to hook into. Every job/scheduler
    function that touches the DB must use this (not `SessionLocal()`
    directly), or RLS will silently return zero rows instead of raising,
    since job code has no per-user context to satisfy the ownership
    policies."""
    async with SessionLocal() as session:
        await session.execute(text("SELECT set_config('app.is_system_context', 'true', true)"))
        yield session

