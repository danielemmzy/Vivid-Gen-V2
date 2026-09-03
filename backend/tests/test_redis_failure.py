"""Chaos-testing Test 6 — Redis failure.

Doesn't need a real Redis at all — the point is to prove the *documented*
degradation policy actually fires when the Redis client raises, which is
exactly what killing the real container would trigger. Three deliberately
different behaviors, matching the module docstrings in core/cache.py and
middleware/rate_limit.py:

  * cache reads/writes -> fail OPEN (always fall through to the loader)
  * rate limiting on an "expensive" endpoint (generation submission)
    -> fail CLOSED (503)
  * rate limiting on an ordinary read endpoint -> fail OPEN
"""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from fastapi.datastructures import Headers

from app.core.cache import cache_get_or_set
from app.middleware import rate_limit as rate_limit_module


class _ExplodingRedis:
    """Stands in for a Redis client whose connection is down — every
    method raises, the way redis-py does on a dead connection."""

    def get(self, *_a, **_kw):
        raise ConnectionError("Redis is unreachable")

    def set(self, *_a, **_kw):
        raise ConnectionError("Redis is unreachable")

    def pipeline(self, *_a, **_kw):
        raise ConnectionError("Redis is unreachable")

    def delete(self, *_a, **_kw):
        raise ConnectionError("Redis is unreachable")


def _fake_request(path: str) -> Request:
    scope = {
        "type": "http", "method": "GET", "path": path, "headers": Headers({}).raw,
        "client": ("127.0.0.1", 12345), "query_string": b"",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_cache_fails_open_when_redis_is_down(monkeypatch):
    monkeypatch.setattr("app.core.cache._client", lambda: _ExplodingRedis())
    loader_calls = []

    async def loader():
        loader_calls.append(1)
        return {"models": ["still works"]}

    result = await cache_get_or_set("some:key", 60, loader)
    assert result == {"models": ["still works"]}
    assert loader_calls == [1], "Cache outage should transparently fall through to the loader, not raise"


@pytest.mark.asyncio
async def test_rate_limit_fails_closed_for_generation_endpoints_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(rate_limit_module, "_client", lambda: _ExplodingRedis())
    request = _fake_request("/api/v1/generations/text-to-image")

    with pytest.raises(HTTPException) as exc_info:
        await rate_limit_module.enforce_rate_limit(request, "user_1", endpoint="/generations/text-to-image")
    assert exc_info.value.status_code == 503, "Generation submission must fail CLOSED during a Redis outage, not silently allow unlimited unmetered spend"


@pytest.mark.asyncio
async def test_rate_limit_fails_open_for_ordinary_reads_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(rate_limit_module, "_client", lambda: _ExplodingRedis())
    request = _fake_request("/api/v1/credits/balance")

    # Must NOT raise — a transient Redis blip shouldn't take down cheap,
    # non-cost-bearing read endpoints.
    await rate_limit_module.enforce_rate_limit(request, "user_1", endpoint="/credits/balance")
