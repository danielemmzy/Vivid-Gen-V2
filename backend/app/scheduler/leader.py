"""Distributed leader election for the scheduler, via a Redis lock with a
renewed TTL. Fixes the scaling gap the architecture review called out: the
scheduler used to run inside the FastAPI app's lifespan, which means N API
replicas would each run their own reconciliation sweep concurrently —
wasted work at best, a race on the same "stuck" rows at worst. Now the
scheduler runs as its own standalone process (see scheduler/run.py, and
docker-compose's `scheduler` service) and this lock ensures that even if
you start more than one instance of that process, only one actually does
the work at a time; a crashed leader's lock expires and another replica
picks it up automatically within LOCK_TTL_SECONDS.
"""
import asyncio
import uuid

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_LOCK_KEY = "vividgen:scheduler:leader"
_LOCK_TTL_SECONDS = 30
_RENEW_INTERVAL_SECONDS = 10


async def run_as_leader_or_wait(stop_event: asyncio.Event) -> bool:
    """Attempts to acquire leadership. Returns True if this process should
    run the scheduler loop (and keeps renewing the lock in the background
    for as long as it holds it), False if another process already holds
    it and this one should just wait/retry."""
    client = redis.from_url(settings.redis_url, decode_responses=True)
    token = uuid.uuid4().hex
    acquired = await client.set(_LOCK_KEY, token, nx=True, ex=_LOCK_TTL_SECONDS)
    if not acquired:
        return False

    async def _renew():
        while not stop_event.is_set():
            await asyncio.sleep(_RENEW_INTERVAL_SECONDS)
            current = await client.get(_LOCK_KEY)
            if current == token:
                await client.expire(_LOCK_KEY, _LOCK_TTL_SECONDS)
            else:
                logger.error("scheduler_lock_lost", token=token)
                return

    asyncio.create_task(_renew())
    logger.info("scheduler_leader_acquired", token=token)
    return True
