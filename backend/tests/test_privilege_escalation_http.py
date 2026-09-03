"""Chaos-testing Test 2 — privilege escalation, full HTTP integration
version (the unit-level check already existed in test_authorization.py;
this exercises the real FastAPI app end to end, over the real ASGI
transport, hitting a real admin-only route).

No database is touched by this test: `require_role`'s dependency chain
(current_principal -> require_internal_user) is a route-level dependency
that FastAPI resolves before the route function's own `system_db_session`
parameter, so a 401 here happens before any DB connection would even be
attempted — see app/dependencies.py's docstring on dependency ordering.
"""
import hashlib
import hmac
import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


def _sign(uid: str, ts: str, role: str) -> str:
    return hmac.new(settings.internal_api_secret.encode(), f"{uid}:{ts}:{role}".encode(), hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_forged_admin_role_header_with_original_user_signature_is_rejected():
    """The exact attack from the audit: take a legitimately-signed
    request for role='user' and change only the X-Vivid-Role header to
    'admin', keeping the original signature. Expected: 401, not 403 —
    the signature simply doesn't validate for the tampered payload, so
    the request never gets far enough to reach a role check at all."""
    user_id = "user_attacker"
    timestamp = str(int(time.time()))
    signature_for_user_role = _sign(user_id, timestamp, "user")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/generations/flagged",
            headers={
                "X-Vivid-User-ID": user_id,
                "X-Vivid-Timestamp": timestamp,
                "X-Vivid-Role": "admin",  # tampered — signature below was computed for "user"
                "X-Vivid-Signature": signature_for_user_role,
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_correctly_signed_non_admin_role_is_forbidden_not_unauthorized():
    """A genuinely, correctly signed role='user' request hitting an
    admin-only route should be turned away for lacking permission (403),
    distinct from an invalid-signature case (401) — this is what proves
    require_role is actually being enforced, not just that auth works."""
    user_id = "user_ordinary"
    timestamp = str(int(time.time()))
    signature = _sign(user_id, timestamp, "user")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/generations/flagged",
            headers={
                "X-Vivid-User-ID": user_id,
                "X-Vivid-Timestamp": timestamp,
                "X-Vivid-Role": "user",
                "X-Vivid-Signature": signature,
            },
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_correctly_signed_admin_role_is_allowed_through_the_auth_layer():
    """Positive control for the two tests above: a correctly signed
    role='admin' request must NOT be rejected at the auth/role layer.
    (It may still fail past that point with a DB error in a unit-test
    environment with no real Postgres — this only asserts we don't get
    401/403, i.e. that the auth layer itself isn't over-blocking.)"""
    user_id = "user_real_admin"
    timestamp = str(int(time.time()))
    signature = _sign(user_id, timestamp, "admin")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/generations/flagged",
            headers={
                "X-Vivid-User-ID": user_id,
                "X-Vivid-Timestamp": timestamp,
                "X-Vivid-Role": "admin",
                "X-Vivid-Signature": signature,
            },
        )
    assert response.status_code not in (401, 403)
