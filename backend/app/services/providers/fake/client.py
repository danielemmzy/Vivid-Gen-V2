"""A fake provider that costs nothing and calls no external API — this is
how you exercise the ENTIRE pipeline (reserve credits -> submit -> webhook
-> finalize job -> charge credits) locally without spending a single fal.ai
credit and without any internet access at all. It satisfies the same
GenerationProvider Protocol as FalProvider, so GenerationService can't tell
the difference; only providers/registry.py knows which one is active,
chosen by GENERATION_PROVIDER=fake.

How it fakes the async webhook flow: submit_* returns immediately with a
fake provider_request_id, then schedules a short-lived asyncio task that
calls the *same* `handle_fal_webhook` handler the real fal.ai webhook route
calls — with a synthetic payload pointing at a local fixture file (see
fixtures/sample.png, fixtures/sample.mp4 — tiny, real, valid media files
committed to the repo) via a `file://` URL. jobs/generation.py's
`_download` helper special-cases `file://` so this never touches the
network: no Wikimedia, no samplelib, nothing that could flake in CI or
during a genuinely offline test run.

Never enable this outside development: see the settings.app_env guard in
providers/registry.py.
"""
import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.database import system_session
from app.core.logging import get_logger
from app.services.providers.base import ProviderSubmission

logger = get_logger(__name__)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SAMPLE_IMAGE_URL = f"file://{_FIXTURES_DIR / 'sample.png'}"
_SAMPLE_VIDEO_URL = f"file://{_FIXTURES_DIR / 'sample.mp4'}"

_FAKE_COMPLETION_DELAY_SECONDS = 3


async def _simulate_completion(provider_request_id: str, is_video: bool) -> None:
    await asyncio.sleep(_FAKE_COMPLETION_DELAY_SECONDS)
    from app.webhooks.fal import handle_fal_webhook  # local import avoids a circular import at module load

    payload: dict[str, Any] = {"request_id": provider_request_id, "status": "COMPLETED", "payload": {}}
    if is_video:
        payload["payload"]["video"] = {"url": _SAMPLE_VIDEO_URL, "content_type": "video/mp4"}
    else:
        payload["payload"]["images"] = [{"url": _SAMPLE_IMAGE_URL, "content_type": "image/png"}]

    async with system_session() as session:
        try:
            await handle_fal_webhook(session, payload)
        except Exception as exc:  # noqa: BLE001 - a broken fake shouldn't crash the dev server
            logger.error("fake_provider_simulation_failed", request_id=provider_request_id, error=str(exc))


def _fake_submit(is_video: bool) -> ProviderSubmission:
    request_id = f"fake_{uuid4().hex}"
    asyncio.create_task(_simulate_completion(request_id, is_video))
    logger.info("fake_provider_submitted", request_id=request_id, will_complete_in_seconds=_FAKE_COMPLETION_DELAY_SECONDS)
    return ProviderSubmission(provider_request_id=request_id, raw={"fake": True})


class FakeProvider:
    """Zero-cost stand-in for FalProvider — see module docstring."""
    name = "fake"

    async def submit_text_to_image(self, provider_model_id: str, prompt: str, **kwargs: Any) -> ProviderSubmission:
        return _fake_submit(is_video=False)

    async def submit_image_to_image(self, provider_model_id: str, prompt: str, image_url: str, **kwargs: Any) -> ProviderSubmission:
        return _fake_submit(is_video=False)

    async def submit_text_to_video(self, provider_model_id: str, prompt: str, **kwargs: Any) -> ProviderSubmission:
        return _fake_submit(is_video=True)

    async def submit_image_to_video(self, provider_model_id: str, prompt: str, image_url: str, **kwargs: Any) -> ProviderSubmission:
        return _fake_submit(is_video=True)

    async def submit_avatar(self, provider_model_id: str, image_url: str, audio_url: str, **kwargs: Any) -> ProviderSubmission:
        return _fake_submit(is_video=True)

    async def submit_video_translation(self, provider_model_id: str, video_url: str, target_language: str, **kwargs: Any) -> ProviderSubmission:
        return _fake_submit(is_video=True)

    async def submit_audio_replace(self, provider_model_id: str, video_url: str, audio_url: str, **kwargs: Any) -> ProviderSubmission:
        return _fake_submit(is_video=True)


fake_provider = FakeProvider()
