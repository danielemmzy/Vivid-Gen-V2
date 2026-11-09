"""Immutable evidence imported from provider usage exports or invoices.

An estimate or runtime callback is not an invoice. This table records externally
reported costs separately so financial reconciliation never silently upgrades an
estimate into a provider-reported amount.
"""
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProviderCostRecord(Base):
    __tablename__ = "provider_cost_record"
    __table_args__ = (
        UniqueConstraint("provider", "external_reference", name="uq_provider_cost_external_reference"),
        Index("ix_provider_cost_generation", "generation_id"),
        Index("ix_provider_cost_reconciliation_status", "reconciliation_status"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    generation_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("generation.id", ondelete="SET NULL"))
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    provider_model_id: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(128), nullable=False)  # invoice, usage_export, provider_api
    invoice_reference: Mapped[str | None] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    reported_cost_usd: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 8))
    variance_usd: Mapped[float | None] = mapped_column(Numeric(18, 8))
    reconciliation_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unmatched")
    raw_record: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

