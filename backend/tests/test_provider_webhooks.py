import base64
import time

import pytest
from nacl.signing import SigningKey

from app.core.config import settings
from app.services.providers.fal import webhook as fal_webhook
from app.services.providers.modal.webhook import (
    sign_modal_payload,
    verify_modal_webhook,
)


def test_modal_signature_accepts_exact_body_and_timestamp(monkeypatch):
    monkeypatch.setattr(settings, "modal_webhook_secret", "local-test-secret")
    body = b'{"call_id":"call-1","status":"completed"}'
    timestamp = str(int(time.time()))

    signature = sign_modal_payload(body, timestamp)

    assert verify_modal_webhook(timestamp, signature, body)
    assert not verify_modal_webhook(timestamp, signature, body + b" ")
    assert not verify_modal_webhook(timestamp, None, body)


def test_modal_signature_rejects_stale_or_missing_secret(monkeypatch):
    monkeypatch.setattr(settings, "modal_webhook_secret", "local-test-secret")
    body = b"{}"
    stale = str(int(time.time()) - 301)
    signature = sign_modal_payload(body, stale)

    assert not verify_modal_webhook(stale, signature, body)

    monkeypatch.setattr(settings, "modal_webhook_secret", "")
    assert not verify_modal_webhook(str(int(time.time())), "anything", body)


@pytest.mark.asyncio
async def test_fal_signature_verifies_body_hash_and_rejects_stale(monkeypatch):
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key.encode()
    request_id = "request-1"
    user_id = "user-1"
    timestamp = str(int(time.time()))
    body = b'{"status":"OK"}'
    message = "\n".join(
        [request_id, user_id, timestamp, fal_webhook.hashlib.sha256(body).hexdigest()]
    ).encode()
    signature = signing_key.sign(message).signature.hex()

    async def jwks():
        return [{"x": base64.urlsafe_b64encode(verify_key).decode().rstrip("=")}]

    monkeypatch.setattr(fal_webhook, "_jwks", jwks)
    assert await fal_webhook.verify_fal_webhook(request_id, user_id, timestamp, signature, body)
    assert not await fal_webhook.verify_fal_webhook(request_id, user_id, timestamp, signature, body + b" ")
    stale = str(int(time.time()) - settings.fal_webhook_tolerance_seconds - 1)
    assert not await fal_webhook.verify_fal_webhook(request_id, user_id, stale, signature, body)
