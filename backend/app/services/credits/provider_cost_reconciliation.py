"""Idempotent import/reconciliation of externally reported provider costs.

This service intentionally does not alter user credits. Provider spend accounting
is distinct from retail credit charging, and invoice records must not trigger a
second generation charge/refund. Call it from a trusted billing-export importer
using a system-context database session.
"""
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation import Generation
from app.models.provider_cost_record import ProviderCostRecord

VALID_SOURCES = {"invoice", "usage_export", "provider_api"}


class ProviderCostReconciliationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def import_record(
        self, *, provider: str, external_reference: str, reported_cost_usd: Decimal | float | str,
        source_type: str, generation_id: str | None = None, provider_request_id: str | None = None,
        provider_model_id: str | None = None, invoice_reference: str | None = None,
        currency: str = "USD", raw_record: dict | None = None, variance_tolerance_usd: Decimal = Decimal("0.01"),
    ) -> tuple[ProviderCostRecord, bool]:
        if source_type not in VALID_SOURCES:
            raise ValueError(f"source_type must be one of {sorted(VALID_SOURCES)}")
        if not provider or not external_reference or len(external_reference) > 255:
            raise ValueError("provider and a stable external_reference are required")
        amount = Decimal(str(reported_cost_usd))
        if not amount.is_finite() or amount < 0:
            raise ValueError("reported_cost_usd must be a finite non-negative amount")
        if currency.upper() != "USD":
            raise ValueError("Only USD provider cost records are supported until explicit FX conversion is implemented")

        existing = (await self.session.execute(select(ProviderCostRecord).where(
            ProviderCostRecord.provider == provider,
            ProviderCostRecord.external_reference == external_reference,
        ))).scalar_one_or_none()
        if existing:
            return existing, False

        generation = None
        if generation_id:
            generation = await self.session.get(Generation, generation_id)
        elif provider_request_id:
            generation = (await self.session.execute(select(Generation).where(
                Generation.provider_request_id == provider_request_id
            ))).scalar_one_or_none()
        estimate = Decimal(str(generation.estimated_provider_cost_usd)) if generation else None
        variance = amount - estimate if estimate is not None else None
        status = "unmatched" if generation is None else (
            "matched" if abs(variance or Decimal(0)) <= variance_tolerance_usd else "variance_review"
        )
        record = ProviderCostRecord(
            id=uuid4().hex, provider=provider, external_reference=external_reference,
            generation_id=generation.id if generation else None, provider_request_id=provider_request_id,
            provider_model_id=provider_model_id, source_type=source_type,
            invoice_reference=invoice_reference, currency="USD", reported_cost_usd=amount,
            estimated_cost_usd=estimate, variance_usd=variance, reconciliation_status=status,
            raw_record=raw_record or {},
        )
        # Savepoint isolates a concurrent duplicate import. The unique database
        # constraint is the final idempotency guard; on conflict, return the
        # already-committed record without poisoning the caller's transaction.
        try:
            async with self.session.begin_nested():
                self.session.add(record)
                await self.session.flush()
            return record, True
        except IntegrityError:
            existing = (await self.session.execute(select(ProviderCostRecord).where(
                ProviderCostRecord.provider == provider,
                ProviderCostRecord.external_reference == external_reference,
            ))).scalar_one_or_none()
            if existing:
                return existing, False
            raise
