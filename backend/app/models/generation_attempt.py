"""gap-closure (0007): GenerationAttempt.

Additive per-attempt audit history alongside the existing
`Generation.retry_count`/`attempted_model_ids` counters (round 2's retry/
fallback wiring in services/generation/service.py) â€” per the explicit
decision to keep the working billing/retry-loop control logic on
`Generation` untouched, rather than refactor it to make `GenerationAttempt`
the thing that actually drives execution. This table is the queryable
"what happened on every individual try" record that was previously only
implicit in `Generation.retry_count` being an integer with no detail
behind it. One row is appended per submission try (including fallback
resubmissions that update the *same* `Generation` row's `provider_request_id`
under round-2's design) â€” see services/generation/service.py's `create()`
and `handle_provider_error()`, which now write to this table."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class GenerationAttempt(Base):
    __tablename__ = "generation_attempt"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    generation_id: Mapped[str] = mapped_column(String(128), ForeignKey("generation.id", ondelete="CASCADE"), index=True)
    production_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("production.id", ondelete="CASCADE"), index=True)
    production_task_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("production_task.id", ondelete="SET NULL"))
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    attempt_number: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str | None] = mapped_column(String(128))
    model_id: Mapped[str | None] = mapped_column(String(64))
    # status: app.core.constants.GenerationAttemptStatus
    status: Mapped[str] = mapped_column(String(128), default="submitted")
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 8))
    actual_cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 8))
    actual_cost_source: Mapped[str | None] = mapped_column(String(40))
    # failure_type: app.core.constants.ProviderErrorClass, if status == "failed"
    failure_type: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str | None] = mapped_column(Text)
    request_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

