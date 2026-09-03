"""Generic Redis-backed read cache. Addresses the "Redis is only used for
rate limiting and ARQ" gap from the architecture review — this is a
thin, explicit cache-aside helper, not a magic decorator that hides what's
cached. Use it for read-heavy, slow-changing data: the model catalog,
feature flags, public config. Never cache anything containing another
user's data behind a key that doesn't include the user id, and never
cache credit balances or anything else that must be read-your-writes
consistent — those stay uncached and hit Postgres directly.
"""
import json
from typing import Any, Awaitable, Callable

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.monitoring.metrics import cache_errors_total

logger = get_logger(__name__)
_redis: redis.Redis | None = None


def _client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def cache_get_or_set(key: str, ttl_seconds: int, loader: Callable[[], Awaitable[Any]]) -> Any:
    client = _client()
    try:
        cached = await client.get(key)
        if cached is not None:
            return json.loads(cached)
    except Exception as exc:  # noqa: BLE001 - a cache outage must degrade to "always load fresh", never break the request
        cache_errors_total.labels(operation="read").inc()
        logger.warning("cache_read_failed", key=key, error=str(exc))

    value = await loader()
    try:
        await client.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        cache_errors_total.labels(operation="write").inc()
        logger.warning("cache_write_failed", key=key, error=str(exc))
    return value


async def cache_invalidate(key: str) -> None:
    try:
        await _client().delete(key)
    except Exception as exc:  # noqa: BLE001
        cache_errors_total.labels(operation="invalidate").inc()
        logger.warning("cache_invalidate_failed", key=key, error=str(exc))
