"""gap-closure (0007): ProductionBudget lifecycle service.

Explicitly additive, per the round-3 decision: CreditService/
CreditTransaction (services/credits/service.py) remain the ONLY system
that actually moves credits into/out of a user's balance — this service
never calls CreditService.reserve/refund directly. What it does is track
the SAME movements from the production's point of view, in a
ProductionBudget row + ProductionBudgetLedger, so "why does this
production's budget say X" has a real audit trail instead of being
implicit in a scatter of `Generation.credits_reserved`/`credits_charged`
fields with no production-level rollup.

Lifecycle:
    estimate_and_create   -- at approve-plan time, before anything is
                              reserved. Records the ESTIMATE.
    reserve                -- at /generate time. Re-checks the balance
                              (the actual per-generation row-locked
                              reservation still happens inside
                              GenerationService.create, unchanged) and
                              records the RESERVE checkpoint.
    record_charge           -- called once per generation as it
    record_refund              completes/fails/is cancelled (jobs/
                              generation.py, services/generation/
                              service.py) — the actual credit movement
                              already happened in CreditService; this
                              appends the matching ledger entry.
    reconcile_on_completion -- called by scheduler.py when the
    reconcile_on_failure        production reaches a terminal state.
                              Flips ProductionBudget.status; does NOT
                              move any credits itself (that already
                              happened incrementally above) — this
                              would double-refund if it did.
"""
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ProductionBudgetLedgerType, ProductionBudgetStatus
from app.core.exceptions import InsufficientProductionBudgetError, ProductionBudgetNotFoundError
from app.core.logging import get_logger
from app.models.production_budget import ProductionBudget, ProductionBudgetLedger
from app.services.credits.service import CreditService

logger = get_logger(__name__)


class ProductionBudgetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.credits = CreditService(session)

    async def get_for_production(self, production_id: str) -> ProductionBudget | None:
        return (
            await self.session.execute(select(ProductionBudget).where(ProductionBudget.production_id == production_id))
        ).scalar_one_or_none()

    async def _append_ledger(
        self, budget: ProductionBudget, *, type_: str, amount: int,
        reference_type: str | None = None, reference_id: str | None = None,
    ) -> None:
        # Charge/refund callbacks can be replayed after worker restarts or
        # duplicate provider events. Make the production ledger idempotent
        # by generation + movement type. Generation finalization takes a
        # row lock on the Generation record, serializing duplicate callbacks.
        if reference_type == "generation" and reference_id:
            existing = await self.session.execute(select(ProductionBudgetLedger.id).where(
                ProductionBudgetLedger.production_id == budget.production_id,
                ProductionBudgetLedger.type == type_,
                ProductionBudgetLedger.reference_type == reference_type,
                ProductionBudgetLedger.reference_id == reference_id,
            ).limit(1))
            if existing.scalar_one_or_none():
                return
        self.session.add(ProductionBudgetLedger(
            id="pbl_" + uuid4().hex, production_id=budget.production_id, budget_id=budget.id, user_id=budget.user_id,
            type=type_, amount=amount, reference_type=reference_type, reference_id=reference_id,
        ))

    async def estimate_and_create(
        self, *, production_id: str, project_id: str, user_id: str, estimated_credits: int,
        budget_profile: str = "short_form", max_shots: int = 20, max_retries_per_shot: int = 1,
    ) -> ProductionBudget:
        budget = ProductionBudget(
            id="pbud_" + uuid4().hex, production_id=production_id, project_id=project_id, user_id=user_id,
            estimated_credits=estimated_credits, status=ProductionBudgetStatus.ESTIMATED,
            budget_profile=budget_profile, max_shots=max_shots, max_retries_per_shot=max_retries_per_shot,
        )
        self.session.add(budget)
        await self.session.flush()
        await self._append_ledger(budget, type_=ProductionBudgetLedgerType.ESTIMATE, amount=estimated_credits)
        await self.session.commit()
        logger.info("production_budget_estimated", production_id=production_id, estimated_credits=estimated_credits)
        return budget

    async def reserve(self, production_id: str) -> ProductionBudget:
        budget = await self.get_for_production(production_id)
        if not budget:
            raise ProductionBudgetNotFoundError("No budget estimate exists for this production", details={"production_id": production_id})

        balance = await self.credits.balance(budget.user_id)
        if balance < budget.estimated_credits:
            raise InsufficientProductionBudgetError(
                f"This production needs an estimated {budget.estimated_credits} credits, you have {balance}",
                details={"estimated_credits": budget.estimated_credits, "available_credits": balance, "production_id": production_id},
            )
        budget.reserved_credits = budget.estimated_credits
        budget.status = ProductionBudgetStatus.RESERVED
        await self._append_ledger(budget, type_=ProductionBudgetLedgerType.RESERVE, amount=budget.estimated_credits)
        await self.session.commit()
        logger.info("production_budget_reserved", production_id=production_id, reserved_credits=budget.reserved_credits)
        return budget

    async def record_charge(self, production_id: str | None, *, generation_id: str, amount: int) -> None:
        if not production_id or amount == 0:
            return
        budget = await self.get_for_production(production_id)
        if not budget:
            return  # a standalone generation somehow carried a production_id with no budget row — log-worthy but not fatal
        existing = await self.session.execute(select(ProductionBudgetLedger.id).where(
            ProductionBudgetLedger.production_id == production_id,
            ProductionBudgetLedger.type == ProductionBudgetLedgerType.CHARGE,
            ProductionBudgetLedger.reference_type == "generation",
            ProductionBudgetLedger.reference_id == generation_id,
        ).limit(1))
        if existing.scalar_one_or_none():
            return
        budget.consumed_credits += amount
        if budget.status == ProductionBudgetStatus.RESERVED:
            budget.status = ProductionBudgetStatus.EXECUTING
        await self._append_ledger(budget, type_=ProductionBudgetLedgerType.CHARGE, amount=amount, reference_type="generation", reference_id=generation_id)
        await self.session.commit()

    async def record_refund(self, production_id: str | None, *, generation_id: str, amount: int) -> None:
        if not production_id or amount == 0:
            return
        budget = await self.get_for_production(production_id)
        if not budget:
            return
        existing = await self.session.execute(select(ProductionBudgetLedger.id).where(
            ProductionBudgetLedger.production_id == production_id,
            ProductionBudgetLedger.type == ProductionBudgetLedgerType.REFUND,
            ProductionBudgetLedger.reference_type == "generation",
            ProductionBudgetLedger.reference_id == generation_id,
        ).limit(1))
        if existing.scalar_one_or_none():
            return
        budget.refunded_credits += amount
        await self._append_ledger(budget, type_=ProductionBudgetLedgerType.REFUND, amount=amount, reference_type="generation", reference_id=generation_id)
        await self.session.commit()

    async def _release_unused_reservation(self, budget: ProductionBudget) -> int:
        already_released_result = await self.session.execute(
            select(func.coalesce(func.sum(ProductionBudgetLedger.amount), 0)).where(
                ProductionBudgetLedger.production_id == budget.production_id,
                ProductionBudgetLedger.type == ProductionBudgetLedgerType.RELEASE,
            )
        )
        already_released = int(already_released_result.scalar_one() or 0)
        unused = max(0, budget.reserved_credits - budget.consumed_credits - budget.refunded_credits - already_released)
        if unused:
            await self._append_ledger(budget, type_=ProductionBudgetLedgerType.RELEASE, amount=unused)
        return unused

    async def reconcile_on_completion(self, production_id: str) -> None:
        budget = await self.get_for_production(production_id)
        if not budget:
            return
        released = await self._release_unused_reservation(budget)
        budget.status = ProductionBudgetStatus.RECONCILED
        await self.session.commit()
        logger.info(
            "production_budget_reconciled", production_id=production_id, reserved=budget.reserved_credits,
            consumed=budget.consumed_credits, refunded=budget.refunded_credits, released=released,
        )

    async def reconcile_on_failure(self, production_id: str) -> None:
        """Does NOT move credits — every generation that actually
        reserved credits already refunded its own unspent portion via
        services/generation/service.py's fail/cancel paths (which call
        `record_refund` above with the real amount). This just closes
        out the budget's own status so it doesn't sit at RESERVED/
        EXECUTING forever."""
        budget = await self.get_for_production(production_id)
        if not budget:
            return
        released = await self._release_unused_reservation(budget)
        budget.status = ProductionBudgetStatus.FAILED
        await self.session.commit()
        logger.info("production_budget_failed", production_id=production_id, released=released)

    async def resume_after_failure(self, production_id: str, *, additional_estimated_credits: int = 0) -> ProductionBudget:
        """Re-open the audit lifecycle and re-reserve only retry work.

        The reserve here is a production-level estimate/checkpoint, not a
        second movement of the user's balance. Each actual retry still gets
        its own row-locked balance reservation in GenerationService.create.
        """
        budget = await self.get_for_production(production_id)
        if not budget:
            raise ProductionBudgetNotFoundError("No budget exists for this production", details={"production_id": production_id})
        additional = max(0, int(additional_estimated_credits))
        balance = await self.credits.balance(budget.user_id)
        if balance < additional:
            raise InsufficientProductionBudgetError(
                f"Retrying the failed shots needs an estimated {additional} credits, you have {balance}.",
                details={"estimated_retry_credits": additional, "available_credits": balance, "production_id": production_id},
            )
        if additional:
            budget.estimated_credits += additional
            budget.reserved_credits += additional
            await self._append_ledger(budget, type_=ProductionBudgetLedgerType.RESERVE, amount=additional,
                                      reference_type="production_retry", reference_id=production_id)
        budget.status = ProductionBudgetStatus.EXECUTING
        await self._append_ledger(
            budget, type_=ProductionBudgetLedgerType.ADJUSTMENT, amount=0,
            reference_type="production_resume", reference_id=production_id,
        )
        logger.info("production_budget_resumed", production_id=production_id, profile=budget.budget_profile,
                    additional_estimated_credits=additional)
        return budget
