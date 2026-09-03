from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """All tables here live in the `core` Postgres schema, owned exclusively
    by this service. See app/core/config.py `database_schema` and the
    architecture plan's schema-split decision — never add a table that
    duplicates something Prisma/better-auth already owns (users, sessions).
    The `auth` schema (User, Session, Account, Verification, credits column)
    is migrated by Prisma and only ever touched here via raw parameterized
    SQL in repository/credits.py — never modeled with the ORM."""

    metadata = MetaData(schema=settings.database_schema)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
