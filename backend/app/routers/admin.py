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
from app.models.user_entitlement import UserEntitlement
from app.services.entitlements import PLAN_CATALOG
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone

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


class SetEntitlementRequest(BaseModel):
    plan_key: str = Field(min_length=1, max_length=32)
    overrides: dict | None = None


@router.patch("/entitlements/{user_id}", dependencies=[Depends(require_role("admin", "billing"))])
async def set_user_entitlement(user_id: str, body: SetEntitlementRequest, session: AsyncSession = Depends(system_db_session)):
    if body.plan_key not in PLAN_CATALOG:
        from app.core.exceptions import InvalidGenerationParamsError
        raise InvalidGenerationParamsError("Unknown plan tier", details={"valid_plan_keys": sorted(PLAN_CATALOG)})
    record = await session.get(UserEntitlement, user_id)
    if not record:
        record = UserEntitlement(user_id=user_id, plan_key=body.plan_key, overrides=body.overrides)
        session.add(record)
    else:
        record.plan_key = body.plan_key
        record.overrides = body.overrides
    await session.commit()
    return {"user_id": user_id, "plan_key": record.plan_key, "overrides": record.overrides}


@router.get("/operations/summary", dependencies=[Depends(require_role("admin", "support", "operator"))])
async def operations_summary(session: AsyncSession = Depends(system_db_session)):
    """Small authenticated operational snapshot; detailed timeseries stay in Prometheus /metrics."""
    from app.models.generation import Generation
    from app.models.provider_health import ProviderHealth
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    counts = (await session.execute(
        select(Generation.status, func.count(Generation.id))
        .where(Generation.created_at >= since).group_by(Generation.status)
    )).all()
    providers = (await session.execute(select(ProviderHealth).order_by(ProviderHealth.updated_at.desc()))).scalars().all()
    return {
        "window_hours": 24,
        "generation_counts": {str(status): int(count) for status, count in counts},
        "provider_health": [{"provider": row.provider, "capability": row.capability, "model_id": row.model_id,
                             "status": row.status, "success_count": row.success_count,
                             "failure_count": row.failure_count, "timeout_count": row.timeout_count,
                             "avg_latency_ms": float(row.avg_latency_ms) if row.avg_latency_ms is not None else None,
                             "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
                             "last_failure_at": row.last_failure_at.isoformat() if row.last_failure_at else None}
                            for row in providers],
        "metrics_path": "/metrics",
    }
