"""Credit ledger persistence. The authoritative balance lives on
auth.user.credits in the Next.js/Prisma schema — this service reaches
across schemas with a raw, parameterized UPDATE ... FOR UPDATE rather than
an ORM-mapped cross-schema model, since we deliberately don't want a
SQLAlchemy model here that looks like it owns that table (see Decision 2:
FastAPI owns core, Next.js owns auth). The row lock inside a single
transaction is what makes concurrent reservations for the same user safe."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import CreditTransaction


class InsufficientCreditsRow(Exception):
    def __init__(self, available: int, required: int):
        self.available = available
        self.required = required


class CreditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_balance_for_update(self, user_id: str) -> int:
        result = await self.session.execute(
            text('SELECT credits FROM auth."user" WHERE id = :uid FOR UPDATE'), {"uid": user_id}
        )
        row = result.first()
        if not row:
            raise ValueError(f"User {user_id} not found")
        return int(row[0])

    async def get_balance(self, user_id: str) -> int:
        result = await self.session.execute(text('SELECT credits FROM auth."user" WHERE id = :uid'), {"uid": user_id})
        row = result.first()
        return int(row[0]) if row else 0

    async def set_balance(self, user_id: str, new_balance: int) -> None:
        await self.session.execute(
            text('UPDATE auth."user" SET credits = :balance WHERE id = :uid'),
            {"balance": new_balance, "uid": user_id},
        )

    def record_transaction(self, txn: CreditTransaction) -> None:
        self.session.add(txn)

    async def list_transactions(self, user_id: str, *, limit: int = 100) -> list[dict]:
        rows = (
            await self.session.execute(
                text(
                    "SELECT id, type, amount, balance_before, balance_after, description, created_at "
                    "FROM credit_transaction WHERE user_id = :uid ORDER BY created_at DESC LIMIT :limit"
                ),
                {"uid": user_id, "limit": limit},
            )
        ).mappings().all()
        return [dict(r) for r in rows]
