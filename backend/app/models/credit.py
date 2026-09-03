from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CreditTransaction(Base):
    """Append-only ledger. Balances are never computed by summing this table
    at read time in the hot path (that's O(n) and racy) — the authoritative
    balance lives on auth.user.credits (Next.js schema) and is updated
    transactionally alongside each row here. This table exists for audit,
    dispute resolution, and reconciliation — treat it as immutable."""

    __tablename__ = "credit_transaction"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)
    generation_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("generation.id", ondelete="SET NULL"))

    # type: app.core.constants.CreditTransactionType
    type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)  # negative = debit, positive = credit
    balance_before: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
