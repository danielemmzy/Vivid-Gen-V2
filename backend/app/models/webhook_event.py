from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WebhookEvent(Base):
    """Every inbound provider webhook, logged before processing. Gives us
    (a) a durable idempotency record independent of Generation state â€” so a
    replayed webhook is a no-op even if the Generation row was deleted, and
    (b) an audit trail for debugging 'the provider says X but we show Y'."""

    __tablename__ = "webhook_event"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(128), index=True)
    provider_event_id: Mapped[str] = mapped_column(String(255), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_error: Mapped[str | None] = mapped_column(String(2000))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

