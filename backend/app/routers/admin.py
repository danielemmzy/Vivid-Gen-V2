"""Admin/support tooling, gated by `require_role` rather than plain
`current_user_id` — this is the concrete piece of the "no real RBAC"
finding from the architecture review. Every route here is something an
ordinary user must never be able to call, and every route uses
`system_db_session` (not `db_session`) because an admin adjusting another
user's credits is, by definition, a cross-user operation that RLS's
ownership policy would otherwise block — see the RLS migration's
`app.is_system_context` bypass, which exists specifically for cases like
this, not as a general escape hatch.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ModerationVerdict
from app.dependencies import require_role, system_db_session
from app.repository.generations import GenerationRepository
from app.services.credits.service import CreditService

router = APIRouter(prefix="/admin", tags=["admin"])


class AdjustCreditsRequest(BaseModel):
    user_id: str = Field(min_length=1)
    amount: int = Field(description="Positive to grant, negative to deduct")
    reason: str = Field(min_length=1, max_length=500)


@router.post("/credits/adjust", dependencies=[Depends(require_role("admin", "billing"))])
async def adjust_credits(body: AdjustCreditsRequest, session: AsyncSession = Depends(system_db_session)):
    credit_service = CreditService(session)
    new_balance = await credit_service.admin_adjust(body.user_id, body.amount, body.reason)
    await session.commit()
    return {"user_id": body.user_id, "new_balance": new_balance}


@router.get("/generations/flagged", dependencies=[Depends(require_role("admin", "moderator", "support"))])
async def list_flagged_generations(limit: int = 50, session: AsyncSession = Depends(system_db_session)):
    """Generations the moderation service flagged for human review (not
    hard-blocked — those never got submitted at all) — see
    services/moderation/service.py's FLAG_FOR_REVIEW verdict."""
    from sqlalchemy import select
    from app.models.generation import Generation

    stmt = (
        select(Generation)
        .where(Generation.moderation_verdict == ModerationVerdict.FLAG_FOR_REVIEW)
        .order_by(Generation.created_at.desc())
        .limit(min(limit, 200))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "generations": [
            {"id": r.id, "user_id": r.user_id, "type": r.type, "prompt": r.prompt, "status": r.status, "created_at": r.created_at}
            for r in rows
        ]
    }


@router.get("/users/{user_id}/generations", dependencies=[Depends(require_role("admin", "support"))])
async def list_user_generations_for_support(user_id: str, limit: int = 50, session: AsyncSession = Depends(system_db_session)):
    repo = GenerationRepository(session)
    rows = await repo.list_for_user(user_id, limit=limit)
    return {"generations": [{"id": r.id, "type": r.type, "status": r.status, "created_at": r.created_at} for r in rows]}
