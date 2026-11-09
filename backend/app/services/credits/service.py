"""Credit reservation/charge/refund. Every method assumes it's running
inside a caller-managed transaction (no commit here) — see
GenerationService, which is the only place that owns transaction
boundaries per the architecture plan's Phase 4. This service just does the
row-locked read-modify-write and appends a ledger entry; the caller decides
when to commit or roll back."""
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CreditTransactionType
from app.core.exceptions import InsufficientCreditsError
from app.models.credit import CreditTransaction
from app.repository.credits import CreditRepository


class CreditService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = CreditRepository(session)

    async def balance(self, user_id: str) -> int:
        return await self.repo.get_balance(user_id)

    async def reserve(self, user_id: str, generation_id: str | None, amount: int, description: str) -> int:
        before = await self.repo.get_balance_for_update(user_id)
        if before < amount:
            raise InsufficientCreditsError(
                f"Need {amount} credits, have {before}",
                details={"required_credits": amount, "available_credits": before},
            )
        after = before - amount
        await self.repo.set_balance(user_id, after)
        self.repo.record_transaction(
            CreditTransaction(
                id=uuid4().hex, user_id=user_id, generation_id=generation_id,
                type=CreditTransactionType.GENERATION_RESERVATION, amount=-amount,
                balance_before=before, balance_after=after, description=description,
            )
        )
        return after

    async def refund(self, user_id: str, generation_id: str, amount: int, description: str) -> int:
        if amount <= 0:
            return await self.repo.get_balance(user_id)
        before = await self.repo.get_balance_for_update(user_id)
        after = before + amount
        await self.repo.set_balance(user_id, after)
        self.repo.record_transaction(
            CreditTransaction(
                id=uuid4().hex, user_id=user_id, generation_id=generation_id,
                type=CreditTransactionType.GENERATION_REFUND, amount=amount,
                balance_before=before, balance_after=after, description=description,
            )
        )
        return after

    async def grant(self, user_id: str, amount: int, description: str, txn_type: str = CreditTransactionType.GRANT) -> int:
        """Used by the Polar billing webhook relay (subscription renewal,
        signup bonus, admin adjustment) — never called from the generation
        path, which only reserves/refunds."""
        before = await self.repo.get_balance_for_update(user_id)
        after = before + amount
        await self.repo.set_balance(user_id, after)
        self.repo.record_transaction(
            CreditTransaction(
                id=uuid4().hex, user_id=user_id, generation_id=None, type=txn_type, amount=amount,
                balance_before=before, balance_after=after, description=description,
            )
        )
        return after


    async def grant_purchase_once(self, user_id: str, amount: int, description: str, external_reference: str) -> tuple[int, bool]:
        """Grant a paid credit pack exactly once for a verified Polar order ID.

        Returns (balance, newly_granted). Caller commits the transaction.
        The unique external_reference constraint is the final concurrency guard;
        the pre-check handles ordinary webhook retries without a uniqueness error.
        """
        from sqlalchemy import select
        if amount <= 0 or not external_reference or len(external_reference) > 191:
            raise ValueError("Invalid purchase grant")
        existing = (await self.session.execute(
            select(CreditTransaction).where(CreditTransaction.external_reference == external_reference)
        )).scalar_one_or_none()
        if existing:
            return await self.repo.get_balance(user_id), False
        before = await self.repo.get_balance_for_update(user_id)
        # Re-check after taking the user balance lock to serialize retries for this user.
        existing = (await self.session.execute(
            select(CreditTransaction).where(CreditTransaction.external_reference == external_reference)
        )).scalar_one_or_none()
        if existing:
            return before, False
        after = before + amount
        await self.repo.set_balance(user_id, after)
        self.repo.record_transaction(CreditTransaction(
            id=uuid4().hex, user_id=user_id, generation_id=None,
            type=CreditTransactionType.PURCHASE, amount=amount,
            balance_before=before, balance_after=after, description=description[:500],
            external_reference=external_reference,
        ))
        return after, True

    async def admin_adjust(self, user_id: str, amount: int, description: str) -> int:
        """Positive or negative, always tagged ADMIN_ADJUSTMENT so it's
        distinguishable in the ledger from ordinary generation
        reserve/charge/refund activity or a Polar-driven grant. Used by
        routers/admin.py, gated by require_role — never exposed to
        ordinary users."""
        before = await self.repo.get_balance_for_update(user_id)
        after = before + amount
        if after < 0:
            raise InsufficientCreditsError(
                f"Adjustment would take balance negative (have {before}, adjusting {amount})",
                details={"available_credits": before, "requested_adjustment": amount},
            )
        await self.repo.set_balance(user_id, after)
        self.repo.record_transaction(
            CreditTransaction(
                id=uuid4().hex, user_id=user_id, generation_id=None, type=CreditTransactionType.ADMIN_ADJUSTMENT,
                amount=amount, balance_before=before, balance_after=after, description=description,
            )
        )
        return after

    async def transactions(self, user_id: str, *, limit: int = 100) -> list[dict]:
        return await self.repo.list_transactions(user_id, limit=limit)
