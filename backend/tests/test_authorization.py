import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import require_internal_user


def _sign(uid: str, ts: str, role: str) -> str:
    return hmac.new(settings.internal_api_secret.encode(), f"{uid}:{ts}:{role}".encode(), hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    ts = str(int(time.time()))
    sig = _sign("user_1", ts, "user")
    principal = require_internal_user("user_1", ts, "user", sig)
    assert principal.user_id == "user_1"
    assert principal.role == "user"


def test_missing_headers_rejected():
    with pytest.raises(HTTPException) as exc_info:
        require_internal_user(None, None, None, None)
    assert exc_info.value.status_code == 401


def test_expired_timestamp_rejected():
    old_ts = str(int(time.time()) - settings.internal_auth_tolerance_seconds - 60)
    sig = _sign("user_1", old_ts, "user")
    with pytest.raises(HTTPException) as exc_info:
        require_internal_user("user_1", old_ts, "user", sig)
    assert exc_info.value.status_code == 401


def test_tampered_user_id_rejected():
    """Signature was computed for user_1 but the header now claims user_2
    — this must fail even though the signature itself is well-formed."""
    ts = str(int(time.time()))
    sig = _sign("user_1", ts, "user")
    with pytest.raises(HTTPException) as exc_info:
        require_internal_user("user_2", ts, "user", sig)
    assert exc_info.value.status_code == 401


def test_tampered_role_rejected():
    """Signature was computed for role='user' but the header now claims
    'admin' — the exact privilege-escalation path role-signing exists to
    close."""
    ts = str(int(time.time()))
    sig = _sign("user_1", ts, "user")
    with pytest.raises(HTTPException) as exc_info:
        require_internal_user("user_1", ts, "admin", sig)
    assert exc_info.value.status_code == 401


def test_unknown_role_rejected():
    ts = str(int(time.time()))
    sig = _sign("user_1", ts, "superuser")
    with pytest.raises(HTTPException) as exc_info:
        require_internal_user("user_1", ts, "superuser", sig)
    assert exc_info.value.status_code == 401
