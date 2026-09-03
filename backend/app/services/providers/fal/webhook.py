"""fal.ai webhook signature verification (Ed25519 over JWKS). This logic was
already correct in the original implementation — moved here unchanged in
substance, just relocated under the provider package since webhook
verification is provider-specific and shouldn't live in a generic
app/webhooks/ module."""
import base64
import hashlib
import time

import httpx
from nacl.encoding import HexEncoder  # noqa: F401 - kept for parity with fal's documented example
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

JWKS_URL = "https://rest.fal.ai/.well-known/jwks.json"
_cache: tuple[float, list[dict]] | None = None


async def _jwks() -> list[dict]:
    global _cache
    now = time.time()
    if _cache and now - _cache[0] < 86400:
        return _cache[1]
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(JWKS_URL)
        response.raise_for_status()
        keys = response.json().get("keys", [])
    _cache = (now, keys)
    return keys


async def verify_fal_webhook(
    request_id: str | None, user_id: str | None, timestamp: str | None, signature: str | None, body: bytes
) -> bool:
    if not all((request_id, user_id, timestamp, signature)):
        return False
    try:
        ts = int(timestamp)
        if abs(int(time.time()) - ts) > settings.fal_webhook_tolerance_seconds:
            logger.warning("fal_webhook_stale", request_id=request_id, skew_seconds=abs(int(time.time()) - ts))
            return False
        message = "\n".join([request_id, user_id, timestamp, hashlib.sha256(body).hexdigest()]).encode()
        signature_bytes = bytes.fromhex(signature)
        for key in await _jwks():
            raw = key.get("x")
            if not raw:
                continue
            public_key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            try:
                VerifyKey(public_key).verify(message, signature_bytes)
                return True
            except BadSignatureError:
                continue
    except (ValueError, TypeError, httpx.HTTPError) as exc:
        logger.warning("fal_webhook_verify_error", error=str(exc))
        return False
    return False
