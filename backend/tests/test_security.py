import hashlib
import hmac
import time

from app.core.config import settings
from app.core.security import _expected_signature


def test_internal_signature_includes_role():
    uid, role = "user_123", "user"
    ts = str(int(time.time()))
    expected = hmac.new(settings.internal_api_secret.encode(), f"{uid}:{ts}:{role}".encode(), hashlib.sha256).hexdigest()
    assert _expected_signature(uid, ts, role) == expected


def test_signature_changes_if_role_is_tampered_with():
    """The whole point of signing role alongside user_id: a signature
    computed for role='user' must not validate for role='admin' — this is
    what stops a compromised/buggy Next.js route (or a manually crafted
    request) from privilege-escalating by just changing an unsigned
    header."""
    uid = "user_123"
    ts = str(int(time.time()))
    user_sig = _expected_signature(uid, ts, "user")
    admin_sig = _expected_signature(uid, ts, "admin")
    assert user_sig != admin_sig
