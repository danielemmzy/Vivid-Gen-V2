"""Centralized, inspectable plan entitlements and monthly usage enforcement."""
from datetime import datetime, timezone
from sqlalchemy import func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.exceptions import VividGenError
from app.models.generation import Generation
from app.models.user_entitlement import UserEntitlement
from app.models.project import Project
from app.models.production import Production
from app.models.production_plan import ProductionPlanRecord

PLAN_CATALOG: dict[str, dict] = {
    "free": {"label": "Free", "monthly_video_seconds": settings.free_plan_monthly_video_seconds,
             "max_concurrent_generations": settings.free_plan_max_concurrent_generations,
             "max_project_duration_seconds": settings.free_plan_max_project_duration_seconds,
             "features": ["text_to_video", "image_to_video", "url_to_video", "presentation", "stock_search", "captions", "audio_mixing"]},
    "creator": {"label": "Creator", "monthly_video_seconds": 1800, "max_concurrent_generations": 3,
                 "max_project_duration_seconds": 300,
                 "features": ["text_to_video", "image_to_video", "url_to_video", "presentation", "stock_search", "captions", "audio_mixing", "voice_cloning", "brand_kits", "long_form"]},
    "studio": {"label": "Studio", "monthly_video_seconds": 10000, "max_concurrent_generations": 6,
               "max_project_duration_seconds": 600,
               "features": ["text_to_video", "image_to_video", "url_to_video", "presentation", "stock_search", "captions", "audio_mixing", "voice_cloning", "brand_kits", "priority_queue", "long_form"]},
}
_ACTIVE_STATUSES = ("queued", "reserving_credits", "processing", "postprocessing", "completed")


class EntitlementDenied(VividGenError):
    http_status = 403
    code = "PLAN_ENTITLEMENT_REQUIRED"


def _month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def get_user_entitlement(session: AsyncSession, user_id: str) -> dict:
    record = await session.get(UserEntitlement, user_id)
    plan_key = record.plan_key if record and record.plan_key in PLAN_CATALOG else "free"
    plan = dict(PLAN_CATALOG[plan_key])
    if record and record.overrides:
        # Only allow documented numeric limit overrides; never accept feature lists from user requests.
        for key in ("monthly_video_seconds", "max_concurrent_generations", "max_project_duration_seconds"):
            value = record.overrides.get(key)
            if isinstance(value, int) and value >= 0:
                plan[key] = value
    return {"plan_key": plan_key, **plan, "updated_at": record.updated_at.isoformat() if record else None}


async def get_monthly_usage(session: AsyncSession, user_id: str, *, exclude_project_id: str | None = None) -> dict:
    start = _month_start()
    # Standalone jobs use their verified generation duration. Movie-shot jobs
    # are excluded here because their inference duration can exceed timeline
    # duration; active movie plans reserve their requested duration below.
    standalone = (await session.execute(
        select(func.coalesce(func.sum(Generation.duration_seconds), 0), func.count(Generation.id))
        .where(Generation.user_id == user_id, Generation.project_id.is_(None),
               or_(and_(Generation.status == "completed", or_(Generation.completed_at >= start, Generation.created_at >= start)),
                   and_(Generation.status.in_(("queued", "reserving_credits", "processing", "postprocessing")))))
    )).first()
    project_stmt = select(Project).where(Project.user_id == user_id, Project.completed_at >= start,
                                         Project.output_duration_seconds.is_not(None))
    if exclude_project_id:
        project_stmt = project_stmt.where(Project.id != exclude_project_id)
    completed_projects = (await session.execute(project_stmt)).scalars().all()
    completed_project_seconds = sum(int(float(project.output_duration_seconds or 0)) for project in completed_projects)

    active_plan_stmt = select(ProductionPlanRecord).join(Production, Production.id == ProductionPlanRecord.production_id).where(
        Production.user_id == user_id,
        Production.status.in_(("awaiting_approval", "approved", "queued", "running", "paused")),
    )
    if exclude_project_id:
        active_plan_stmt = active_plan_stmt.where(Production.project_id != exclude_project_id)
    active_plans = (await session.execute(active_plan_stmt)).scalars().all()
    reserved_project_seconds = sum(int((record.plan_json or {}).get("duration_seconds", 0) or 0) for record in active_plans)
    active = (await session.execute(
        select(func.count(Generation.id)).where(
            Generation.user_id == user_id,
            Generation.status.in_(("queued", "reserving_credits", "processing", "postprocessing")),
        )
    )).scalar_one()
    used = int(float(standalone[0] or 0)) + completed_project_seconds + reserved_project_seconds
    return {"period_start": start.isoformat(), "video_seconds_used": used,
            "generations_counted": int(standalone[1] or 0) + len(completed_projects),
            "active_generations": int(active), "reserved_project_seconds": reserved_project_seconds}


async def enforce_generation_entitlement(session: AsyncSession, user_id: str, duration_seconds: int | None) -> dict:
    entitlement = await get_user_entitlement(session, user_id)
    usage = await get_monthly_usage(session, user_id)
    duration = max(1, int(duration_seconds or 5))
    if duration > entitlement["max_project_duration_seconds"]:
        from app.monitoring.metrics import entitlement_block_total
        entitlement_block_total.labels(entitlement["plan_key"], "max_duration").inc()
        raise EntitlementDenied(
            f"Your {entitlement['label']} plan supports up to {entitlement['max_project_duration_seconds']} seconds per generation.",
            details={"plan_key": entitlement["plan_key"], "limit": entitlement["max_project_duration_seconds"], "requested_seconds": duration, "upgrade_required": True},
        )
    if usage["active_generations"] >= entitlement["max_concurrent_generations"]:
        from app.monitoring.metrics import entitlement_block_total
        entitlement_block_total.labels(entitlement["plan_key"], "concurrent_generations").inc()
        raise EntitlementDenied(
            f"Your {entitlement['label']} plan allows {entitlement['max_concurrent_generations']} active generation(s) at a time.",
            details={"plan_key": entitlement["plan_key"], "limit": entitlement["max_concurrent_generations"], "active": usage["active_generations"], "upgrade_required": True},
        )
    if usage["video_seconds_used"] + duration > entitlement["monthly_video_seconds"]:
        from app.monitoring.metrics import entitlement_block_total
        entitlement_block_total.labels(entitlement["plan_key"], "monthly_seconds").inc()
        raise EntitlementDenied(
            f"Your monthly {entitlement['monthly_video_seconds']}-second video allowance would be exceeded. Top up credits or request a plan change.",
            details={"plan_key": entitlement["plan_key"], "monthly_limit_seconds": entitlement["monthly_video_seconds"],
                     "used_seconds": usage["video_seconds_used"], "requested_seconds": duration, "upgrade_required": True},
        )
    return {"entitlement": entitlement, "usage": usage}


async def enforce_project_entitlement(session: AsyncSession, user_id: str, duration_seconds: int, *, exclude_project_id: str | None = None) -> dict:
    entitlement = await get_user_entitlement(session, user_id)
    usage = await get_monthly_usage(session, user_id, exclude_project_id=exclude_project_id)
    if duration_seconds > entitlement["max_project_duration_seconds"]:
        from app.monitoring.metrics import entitlement_block_total
        entitlement_block_total.labels(entitlement["plan_key"], "max_project_duration").inc()
        raise EntitlementDenied(
            f"Your {entitlement['label']} plan supports movies up to {entitlement['max_project_duration_seconds']} seconds.",
            details={"plan_key": entitlement["plan_key"], "limit": entitlement["max_project_duration_seconds"], "requested_seconds": duration_seconds, "upgrade_required": True},
        )
    if usage["video_seconds_used"] + duration_seconds > entitlement["monthly_video_seconds"]:
        from app.monitoring.metrics import entitlement_block_total
        entitlement_block_total.labels(entitlement["plan_key"], "monthly_project_seconds").inc()
        raise EntitlementDenied(
            f"This movie would exceed your remaining monthly video allowance.",
            details={"plan_key": entitlement["plan_key"], "monthly_limit_seconds": entitlement["monthly_video_seconds"],
                     "used_seconds": usage["video_seconds_used"], "requested_seconds": duration_seconds, "upgrade_required": True},
        )
    return {"entitlement": entitlement, "usage": usage}


async def require_plan_feature(session: AsyncSession, user_id: str, feature: str) -> dict:
    entitlement = await get_user_entitlement(session, user_id)
    if feature not in entitlement.get("features", []):
        from app.monitoring.metrics import entitlement_block_total
        entitlement_block_total.labels(entitlement["plan_key"], feature).inc()
        raise EntitlementDenied(
            f"{feature.replace('_', ' ').capitalize()} is not included in your {entitlement['label']} plan.",
            details={"plan_key": entitlement["plan_key"], "feature": feature, "upgrade_required": True},
        )
    return entitlement


async def enforce_production_concurrency(session: AsyncSession, user_id: str, production_id: str) -> dict:
    entitlement = await get_user_entitlement(session, user_id)
    active = (await session.execute(
        select(func.count(Production.id)).where(
            Production.user_id == user_id, Production.id != production_id,
            Production.status.in_(("queued", "running", "paused")),
        )
    )).scalar_one()
    if int(active) >= entitlement["max_concurrent_generations"]:
        from app.monitoring.metrics import entitlement_block_total
        entitlement_block_total.labels(entitlement["plan_key"], "concurrent_productions").inc()
        raise EntitlementDenied(
            f"Your {entitlement['label']} plan allows {entitlement['max_concurrent_generations']} active production(s) at a time.",
            details={"plan_key": entitlement["plan_key"], "limit": entitlement["max_concurrent_generations"], "active_productions": int(active), "upgrade_required": True},
        )
    return {"entitlement": entitlement, "active_productions": int(active)}
