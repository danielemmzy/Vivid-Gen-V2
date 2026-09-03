"""Liveness vs readiness, kept genuinely separate — a common production
mistake is making /health check the database, which then makes the
orchestrator (k8s/ECS) kill and restart a perfectly healthy process during
a brief DB blip. Liveness = is the process alive. Readiness = can it
actually serve traffic right now.

The readiness response never includes raw exception text — a stack trace
or driver error message can leak internal hostnames, port numbers, or
library versions to anyone who can reach this (unauthenticated by design,
since load balancers need to hit it). Full detail goes to structured logs
and Sentry, where only people with access to those systems can see it."""
import redis.asyncio as redis
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)


async def liveness() -> dict:
    return {"status": "ok"}


async def readiness() -> dict:
    checks = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("readiness_check_failed", check="database", error=str(exc))
        checks["database"] = "error"

    try:
        client = redis.from_url(settings.redis_url)
        await client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("readiness_check_failed", check="redis", error=str(exc))
        checks["redis"] = "error"

    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ready" if healthy else "not_ready", "checks": checks}
