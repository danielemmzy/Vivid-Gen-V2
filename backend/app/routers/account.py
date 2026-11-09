from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import current_user_id, db_session
from app.services.entitlements import PLAN_CATALOG, get_monthly_usage, get_user_entitlement
from app.services.credits.service import CreditService
from app.core.config import settings
from app.models.asset import Asset
from app.models.brand_kit import BrandKit
from app.models.generation import Generation
from app.models.project import Project

router = APIRouter(prefix="/account", tags=["account"])


def _json_value(value):
    """Keep exports JSON-safe without leaking signed URLs or secrets."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _row(model, *, excluded: set[str] | None = None) -> dict:
    excluded = excluded or set()
    return {
        column.name: _json_value(getattr(model, column.name))
        for column in model.__table__.columns
        if column.name not in excluded
    }


@router.get("/entitlements")
async def entitlements(user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    return {"current": await get_user_entitlement(session, user_id), "catalog": PLAN_CATALOG,
            "note": "Plan tier changes are assigned through the billing/admin entitlement workflow; buying a credit pack only adds credits."}


@router.get("/usage")
async def usage(user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    entitlement = await get_user_entitlement(session, user_id)
    report = await get_monthly_usage(session, user_id)
    balance = await CreditService(session).balance(user_id)
    report.update({"plan_key": entitlement["plan_key"], "plan_label": entitlement["label"],
                   "monthly_video_seconds_limit": entitlement["monthly_video_seconds"],
                   "remaining_video_seconds": max(0, entitlement["monthly_video_seconds"] - report["video_seconds_used"]),
                   "max_concurrent_generations": entitlement["max_concurrent_generations"],
                   "max_project_duration_seconds": entitlement["max_project_duration_seconds"],
                   "credits_balance": balance, "credit_usd_value": settings.credit_usd_value})
    return report


@router.get("/export")
async def export_account_data(
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(db_session),
):
    """Return an owner-scoped, non-destructive account export.

    Auth tables remain owned by Prisma/Better Auth; this endpoint exports the
    product-side records and current balance without returning passwords,
    session tokens, provider credentials, prompts, or signed URLs.
    """
    balance_result = await session.execute(
        text('SELECT credits FROM auth."user" WHERE id = :uid'), {"uid": user_id}
    )
    balance_row = balance_result.first()
    transactions = [
        {key: _json_value(value) for key, value in item.items()}
        for item in await CreditService(session).transactions(user_id, limit=1000)
    ]

    async def rows(model):
        result = await session.execute(select(model).where(model.user_id == user_id))
        return [_row(item, excluded={"prompt", "metadata_json", "asset_metadata", "output_url"}) for item in result.scalars()]

    return {
        "format": "vivid-gen-v2-account-export",
        "version": 1,
        "user_id": user_id,
        "credits_balance": int(balance_row[0]) if balance_row else 0,
        "credit_transactions": transactions,
        "projects": await rows(Project),
        "generations": await rows(Generation),
        "assets": await rows(Asset),
        "brand_kits": await rows(BrandKit),
        "note": "Authentication records are owned by Better Auth. Media remains in private storage and is not embedded in this export.",
    }
