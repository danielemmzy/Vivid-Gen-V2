"""Auth boundary between Next.js and FastAPI. Next.js signs every internal
request with HMAC over (user_id, timestamp, role) using a shared secret —
see lib/backend.ts on the frontend. This is intentionally the ONLY place
that trust decision is made; everything downstream just receives a
verified user_id/role via FastAPI's dependency injection.

Role is included in the signed message (not sent unsigned and trusted) —
otherwise a compromised or buggy Next.js route could hand an ordinary user
an "admin" header and the backend would have no way to know it was
tampered with. Signing role alongside user_id means role changes still
require Next.js's own auth/session logic to have decided them.

Kept deliberately swappable: if a second frontend needs to call this API
directly later, replace `require_internal_user` with JWT verification
without touching any router or service — they only depend on
`current_user_id`/`current_user_role`, not on how it was derived.
"""
import hashlib
import hmac
import time

from fastapi import Header, HTTPException

from app.core.config import settings

VALID_ROLES = {"user", "admin", "support", "moderator", "billing", "operator"}


def _expected_signature(user_id: str, timestamp: str, role: str) -> str:
    message = f"{user_id}:{timestamp}:{role}".encode()
    return hmac.new(settings.internal_api_secret.encode(), message, hashlib.sha256).hexdigest()


class InternalPrincipal:
    __slots__ = ("user_id", "role")

    def __init__(self, user_id: str, role: str):
        self.user_id = user_id
        self.role = role


def require_internal_user(
    x_vivid_user_id: str | None = Header(default=None),
    x_vivid_timestamp: str | None = Header(default=None),
    x_vivid_role: str | None = Header(default=None),
    x_vivid_signature: str | None = Header(default=None),
) -> InternalPrincipal:
    if not all((x_vivid_user_id, x_vivid_timestamp, x_vivid_signature)):
        raise HTTPException(401, "Missing internal authentication")
    role = x_vivid_role or "user"
    if role not in VALID_ROLES:
        raise HTTPException(401, "Invalid role claim")
    try:
        skew = abs(int(time.time()) - int(x_vivid_timestamp))
    except ValueError as exc:
        raise HTTPException(401, "Invalid internal authentication") from exc
    if skew > settings.internal_auth_tolerance_seconds:
        raise HTTPException(401, "Expired internal authentication")
    expected = _expected_signature(x_vivid_user_id, x_vivid_timestamp, role)
    if not hmac.compare_digest(x_vivid_signature, expected):
        raise HTTPException(401, "Invalid internal authentication")
    return InternalPrincipal(user_id=x_vivid_user_id, role=role)
