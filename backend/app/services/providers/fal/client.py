"""fal.ai implementation of the GenerationProvider Protocol.

Critical fix vs. the original implementation: `fal_client.submit()` is a
*synchronous, blocking* network call. The original code called it directly
inside an `async def` route handler, which blocks the entire event loop —
under load that stalls every other request on the process, not just the
one doing the fal call. Every submit_* method here runs the blocking SDK
call in a worker thread via `asyncio.to_thread`, and wraps it with a short
retry for transient network errors (fal is occasionally flaky on submit,
per community reports) so one blip doesn't fail a user-facing request
that already reserved credits.
"""
import asyncio
from typing import Any

import fal_client

from app.core.config import settings
from app.core.exceptions import ProviderSubmissionError
from app.core.logging import get_logger
from app.services.providers.base import ProviderSubmission

logger = get_logger(__name__)

_TRANSIENT_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 1.5


class FalProvider:
    name = "fal"

    def __init__(self) -> None:
        if not settings.fal_key:
            raise RuntimeError(
                "FAL_KEY is not configured. If you're testing locally without spending fal.ai "
                "credits, set GENERATION_PROVIDER=fake instead of trying to run the real provider."
            )

    async def _submit(self, provider_model_id: str, arguments: dict[str, Any]) -> ProviderSubmission:
        last_error: Exception | None = None
        for attempt in range(_TRANSIENT_RETRIES + 1):
            try:
                handler = await asyncio.to_thread(
                    fal_client.submit, provider_model_id, arguments=arguments, webhook_url=settings.fal_webhook_url
                )
                return ProviderSubmission(provider_request_id=handler.request_id, raw={"model": provider_model_id})
            except Exception as exc:  # noqa: BLE001 - fal_client raises a mix of httpx/custom errors
                last_error = exc
                if attempt < _TRANSIENT_RETRIES:
                    logger.warning("fal_submit_retry", model=provider_model_id, attempt=attempt, error=str(exc))
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
        logger.error("fal_submit_failed", model=provider_model_id, error=str(last_error))
        raise ProviderSubmissionError(
            "fal.ai rejected the generation request", details={"provider": "fal", "model": provider_model_id}
        ) from last_error

    async def submit_text_to_image(self, provider_model_id: str, prompt: str, **kwargs: Any) -> ProviderSubmission:
        return await self._submit(provider_model_id, {"prompt": prompt, **kwargs})

    async def submit_image_to_image(self, provider_model_id: str, prompt: str, image_url: str, **kwargs: Any) -> ProviderSubmission:
        payload = {"prompt": prompt, **kwargs}
        if "image_urls" not in payload:
            payload["image_url"] = image_url
        return await self._submit(provider_model_id, payload)

    async def submit_text_to_video(self, provider_model_id: str, prompt: str, **kwargs: Any) -> ProviderSubmission:
        return await self._submit(provider_model_id, {"prompt": prompt, **kwargs})

    async def submit_image_to_video(self, provider_model_id: str, prompt: str, image_url: str, **kwargs: Any) -> ProviderSubmission:
        payload = {"prompt": prompt, **kwargs}
        if "image_urls" not in payload:
            payload["image_url"] = image_url
        return await self._submit(provider_model_id, payload)

    async def submit_avatar(self, provider_model_id: str, image_url: str, audio_url: str, **kwargs: Any) -> ProviderSubmission:
        return await self._submit(provider_model_id, {"image_url": image_url, "audio_url": audio_url, **kwargs})

    async def submit_video_translation(self, provider_model_id: str, video_url: str, target_language: str, **kwargs: Any) -> ProviderSubmission:
        return await self._submit(provider_model_id, {"video_url": video_url, "target_language": target_language, **kwargs})

    async def submit_audio_replace(self, provider_model_id: str, video_url: str, audio_url: str, **kwargs: Any) -> ProviderSubmission:
        return await self._submit(provider_model_id, {"video_url": video_url, "audio_url": audio_url, **kwargs})
