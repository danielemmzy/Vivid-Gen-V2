"""Modal webhook signature verification. Unlike fal (a third party whose
webhook signing we don't control — Ed25519/JWKS, see fal/webhook.py), the
Modal callback comes from code we deploy ourselves (modal_app/wan_worker.py),
so a shared-secret HMAC is appropriate and much simpler — the same pattern
already used for frontend<->backend internal auth (core/security.py)."""
import hashlib
import hmac
import time

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def sign_modal_payload(body: bytes, timestamp: str) -> str:
    message = timestamp.encode() + b"." + body
    return hmac.new(settings.modal_webhook_secret.encode(), message, hashlib.sha256).hexdigest()


def verify_modal_webhook(timestamp: str | None, signature: str | None, body: bytes) -> bool:
    if not timestamp or not signature or not settings.modal_webhook_secret:
        return False
    try:
        ts = int(timestamp)
        if abs(int(time.time()) - ts) > 300:
            logger.warning("modal_webhook_stale", skew_seconds=abs(int(time.time()) - ts))
            return False
    except ValueError:
        return False
    expected = sign_modal_payload(body, timestamp)
    return hmac.compare_digest(expected, signature)
