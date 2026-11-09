"""Round 4, decision #3 (confirmed): ProviderHealth.

Persistent routing telemetry, incrementally updated whenever a
GenerationAttempt (or a stock/music provider call) resolves â€” not
recomputed by aggregating the full GenerationAttempt history on every
routing decision (gets slower as history grows), and not purely
in-memory (would reset on every worker restart, defeating the point of
"persistent"). GenerationAttempt remains the detailed evidence; this is
the aggregate the routers actually query.

`status` is the explicit availability state the round-4 brief required
(AVAILABLE/NOT_CONFIGURED/TEMPORARILY_UNAVAILABLE/RATE_LIMITED/FAILED â€”
see core/constants.py::ProviderAvailabilityStatus) â€” a missing API key
and a failing API call are different conditions and must be
distinguishable by every router that reads this table, not collapsed
into one boolean."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class ProviderHealth(Base):
    __tablename__ = "provider_health"
    __table_args__ = (UniqueConstraint("provider", "model_id", "capability", name="uq_provider_health_key"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(128), index=True)
    model_id: Mapped[str | None] = mapped_column(String(64))
    capability: Mapped[str | None] = mapped_column(String(128))

    # status: app.core.constants.ProviderAvailabilityStatus
    status: Mapped[str] = mapped_column(String(128), default="available")
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency_ms: Mapped[float | None] = mapped_column(Numeric(10, 2))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

