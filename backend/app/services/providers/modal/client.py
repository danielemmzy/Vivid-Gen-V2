"""V2 Phase 7: Modal-hosted Wan provider.

Architecture:

    ModalProvider.submit_*  (this file, runs in the FastAPI container)
        -> modal.Cls.from_name(..., "WanWorker")().generate.spawn(...)
        -> Modal allocates/reuses a GPU container with one persistent Wan pipeline
        -> that worker uploads the result to S3 and POSTs to /webhooks/modal
        -> app/webhooks/modal.py finalizes the Generation exactly like fal's webhook does

This file does NOT contain the GPU code itself — that's
`modal_app/wan_worker.py`, a separate deployable Modal app (run `modal
deploy modal_app/wan_worker.py` once, independently of this backend's own
deploys). This file only triggers it.

Only text_to_video and image_to_video are implemented, matching Wan
2.2 TI2V's actual documented capabilities (spec §20: "verify exact
capabilities... do not invent endpoints"). The other five
GenerationProvider methods raise UnsupportedByWanError rather than
silently pretending to support them (spec §8).

NOT verified against a real Modal deployment in this session — no Modal
account/credentials available in this sandbox. The `modal` Python SDK
call shapes below (`Function.lookup`, `.spawn`) match Modal's documented
API as of this codebase's training data; confirm against Modal's current
docs and test against a real deployed function before trusting this.
"""
from typing import Any

import modal

from app.core.config import settings
from app.core.exceptions import VividGenError
from app.services.providers.base import ProviderSubmission

_CLASS_NAME = "WanWorker"  # persistent @app.cls in modal_app/wan_worker.py
_METHOD_NAME = "generate"


class ModalSubmissionError(VividGenError):
    http_status = 502
    code = "MODAL_SUBMISSION_FAILED"


class UnsupportedByWanError(VividGenError):
    http_status = 400
    code = "UNSUPPORTED_MODEL_FOR_TYPE"


class ModalProvider:
    name = "modal"

    def __init__(self) -> None:
        if not (settings.modal_token_id and settings.modal_token_secret):
            raise RuntimeError(
                "MODAL_TOKEN_ID/MODAL_TOKEN_SECRET are not configured. A catalog model with "
                "\"provider\": \"modal\" will fail at submission time until these are set — "
                "see V2_ARCHITECTURE_AUDIT.md's Phase 7 section for the full setup checklist."
            )

    async def _spawn(self, mode: str, arguments: dict[str, Any]) -> ProviderSubmission:
        try:
            worker = modal.Cls.from_name(settings.modal_app_name, _CLASS_NAME)()
            method = getattr(worker, _METHOD_NAME)
            arguments = dict(arguments)
            arguments.setdefault("sample_steps", settings.wan_sample_steps)
            call = method.spawn(
                mode=mode, wan_model=settings.wan_model, **arguments
            )
        except Exception as exc:  # noqa: BLE001 — modal SDK raises a mix of its own error types
            raise ModalSubmissionError("Modal function spawn failed", details={"cause": str(exc), "mode": mode}) from exc
        return ProviderSubmission(provider_request_id=call.object_id, raw={"mode": mode, "wan_model": settings.wan_model})

    async def submit_text_to_image(self, provider_model_id: str, prompt: str, **kwargs: Any) -> ProviderSubmission:
        raise UnsupportedByWanError("Wan does not support text_to_image")

    async def submit_image_to_image(self, provider_model_id: str, prompt: str, image_url: str, **kwargs: Any) -> ProviderSubmission:
        raise UnsupportedByWanError("Wan does not support image_to_image")

    async def submit_text_to_video(self, provider_model_id: str, prompt: str, **kwargs: Any) -> ProviderSubmission:
        return await self._spawn("text_to_video", {"prompt": prompt, **kwargs})

    async def submit_image_to_video(self, provider_model_id: str, prompt: str, image_url: str, **kwargs: Any) -> ProviderSubmission:
        return await self._spawn("image_to_video", {"prompt": prompt, "image_url": image_url, **kwargs})

    async def submit_avatar(self, provider_model_id: str, image_url: str, audio_url: str, **kwargs: Any) -> ProviderSubmission:
        raise UnsupportedByWanError("Wan does not support avatar/lip-sync generation")

    async def submit_video_translation(self, provider_model_id: str, video_url: str, target_language: str, **kwargs: Any) -> ProviderSubmission:
        raise UnsupportedByWanError("Wan does not support video translation")

    async def submit_audio_replace(self, provider_model_id: str, video_url: str, audio_url: str, **kwargs: Any) -> ProviderSubmission:
        raise UnsupportedByWanError("Wan does not support audio replacement")
