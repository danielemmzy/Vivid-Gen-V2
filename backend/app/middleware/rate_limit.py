"""Redis-backed rate limiting.

Two things fixed here versus the original implementation, both found
while designing the chaos-testing suite (see tests/integration/test_redis_failure.py):

1. `rate_limit_burst` was defined in settings but never read by the
   limiter, so it had zero effect on behavior. There are now two windows
   enforced together, per user: a 1-second burst window and a 60-second
   sustained window (or an endpoint-specific override from
   settings.endpoint_rate_limits).

2. A Redis outage used to raise an unhandled exception straight out of
   this function, which FastAPI turns into an uncontrolled 500 on every
   single request — effectively an accidental, undocumented "fail closed
   for everything," including cheap reads that have nothing to do with
   generation cost. That's not a deliberate policy, it's just what
   happens when nobody catches the exception. The explicit policy now is:

     - "expensive" endpoints (settings.rate_limit_fail_closed_prefixes —
       generation submission, movie assembly) FAIL CLOSED: a 503 is
       clearer and safer than silently allowing unlimited, unmetered
       provider spend during a Redis outage.
     - everything else FAILS OPEN: a transient Redis blip must not take
       down read endpoints (checking generation status, listing
       creations) that don't carry a cost/abuse risk if unmetered for a
       few seconds.

   Either way the failure is logged and counted (rate_limit_redis_errors_total)
   so an actual outage is visible in monitoring, not just silently absorbed.
"""
import time

import redis.asyncio as redis
from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.logging import get_logger
from app.monitoring.metrics import rate_limit_redis_errors_total

logger = get_logger(__name__)

_redis: redis.Redis | None = None


def _client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
    return _redis


async def _sliding_window_check(key: str, window_seconds: float, limit: int, member_suffix: str) -> int:
    now = time.time()
    window_start = now - window_seconds
    client = _client()
    pipe = client.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zcard(key)
    pipe.zadd(key, {f"{now}:{member_suffix}": now})
    pipe.expire(key, int(window_seconds) + 1)
    _, count, *_ = await pipe.execute()
    return count


def _endpoint_limit(endpoint: str) -> int:
    for suffix, limit in settings.endpoint_rate_limits.items():
        if endpoint.startswith(suffix) or endpoint.endswith(suffix):
            return limit
    return settings.rate_limit_per_minute


def _is_expensive_endpoint(endpoint: str) -> bool:
    return any(endpoint.startswith(prefix) for prefix in settings.rate_limit_fail_closed_prefixes)


async def enforce_rate_limit(request: Request, user_id: str, *, endpoint: str | None = None) -> None:
    endpoint = endpoint or request.url.path
    per_minute_limit = _endpoint_limit(endpoint)
    client_ip = request.client.host if request.client else "unknown"

    try:
        burst_count = await _sliding_window_check(f"vividgen:ratelimit:burst:{user_id}", 1, settings.rate_limit_burst, endpoint)
        if burst_count > settings.rate_limit_burst:
            raise HTTPException(429, "Too many requests in a short burst — please slow down")

        sustained_count = await _sliding_window_check(
            f"vividgen:ratelimit:sustained:{user_id}:{endpoint}", 60, per_minute_limit, endpoint
        )
        if sustained_count > per_minute_limit:
            raise HTTPException(429, "Rate limit exceeded — please slow down")

        ip_count = await _sliding_window_check(f"vividgen:ratelimit:ip:{client_ip}", 60, settings.rate_limit_per_ip_per_minute, endpoint)
        if ip_count > settings.rate_limit_per_ip_per_minute:
            raise HTTPException(429, "Rate limit exceeded for this origin — please slow down")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - redis.exceptions.* plus connection-level OSError variants
        rate_limit_redis_errors_total.labels(endpoint=endpoint).inc()
        logger.error("rate_limit_redis_unavailable", endpoint=endpoint, user_id=user_id, error=str(exc))
        if _is_expensive_endpoint(endpoint):
            raise HTTPException(503, "Rate limiting is temporarily unavailable — please try again shortly") from exc
        # Fail open for cheap reads — see module docstring.
        return
