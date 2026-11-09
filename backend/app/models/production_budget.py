"""gap-closure (0007): ProductionBudget + ProductionBudgetLedger.

Previously "credit preflight" (routers/projects.py's /generate endpoint,
rounds 1-2) computed a total estimate and checked the balance, but there
was no persisted object representing that estimate/reservation/actual-
cost lifecycle for a production as a whole â€” only per-`Generation` fields
(`credits_reserved`, `credits_charged`). This makes that lifecycle a real,
queryable thing: one `ProductionBudget` row per Production, with every
individual movement (an estimate, a reservation, a charge, a refund)
appended to `ProductionBudgetLedger` rather than only ever mutating a
balance field in place â€” so "why does this production's budget say X" has
an actual audit trail, matching how CreditTransaction already works for
the user's overall balance.

This is additive: CreditService/CreditTransaction (the user's actual
credit balance ledger) is unchanged and remains the system that really
moves credits in and out of a user's account. ProductionBudget tracks the
same movements from the production's point of view â€” every reserve/
charge/refund that ProductionBudgetService performs also calls
CreditService, and appends a matching ProductionBudgetLedger row so the
two can be cross-checked."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, _utcnow


class ProductionBudget(Base, TimestampMixin):
    __tablename__ = "production_budget"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    production_id: Mapped[str] = mapped_column(String(128), ForeignKey("production.id", ondelete="CASCADE"), unique=True, index=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    currency: Mapped[str] = mapped_column(String(8), default="credits")
    estimated_credits: Mapped[int] = mapped_column(Integer, default=0)
    reserved_credits: Mapped[int] = mapped_column(Integer, default=0)
    consumed_credits: Mapped[int] = mapped_column(Integer, default=0)
    refunded_credits: Mapped[int] = mapped_column(Integer, default=0)
    # Profile is policy, while credits remain dynamically estimated from the actual shot plan.
    budget_profile: Mapped[str] = mapped_column(String(24), default="short_form")
    max_shots: Mapped[int] = mapped_column(Integer, default=20)
    max_retries_per_shot: Mapped[int] = mapped_column(Integer, default=1)
    # status: app.core.constants.ProductionBudgetStatus
    status: Mapped[str] = mapped_column(String(128), default="estimated")


class ProductionBudgetLedger(Base):
    """Append-only â€” deliberately does NOT use TimestampMixin (no
    `updated_at`; a ledger entry is immutable once written, matching the
    migration's schema, which only defines `created_at` for this table)."""
    __tablename__ = "production_budget_ledger"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    production_id: Mapped[str] = mapped_column(String(128), ForeignKey("production.id", ondelete="CASCADE"), index=True)
    budget_id: Mapped[str] = mapped_column(String(128), ForeignKey("production_budget.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    # type: app.core.constants.ProductionBudgetLedgerType
    type: Mapped[str] = mapped_column(String(128))
    amount: Mapped[int] = mapped_column(Integer)
    reference_type: Mapped[str | None] = mapped_column(String(128))  # "generation" | "production_task" | ...
    reference_id: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

