from datetime import datetime, timezone
from typing import Any
from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserEntitlement(Base):
    __tablename__ = "user_entitlement"
    user_id: Mapped[str] = mapped_column(String(191), primary_key=True)
    plan_key: Mapped[str] = mapped_column(String(128), default="free", nullable=False)
    overrides: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

