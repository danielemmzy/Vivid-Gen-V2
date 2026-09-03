"""The generation orchestrator. This replaces the original `_submit()`
function that lived inline in the router (pricing + DB write + credit
reservation + provider call + manual rollback/begin compensation all in one
45-line function) — the single highest-risk piece of code identified in the
architecture review, since a partial failure there could double-charge or
permanently strand a user's credits.

Two deliberate design choices vs. the original:

1. Two short transactions instead of one long one spanning a network call.
   The original held the DB session across the fal.ai HTTP submission.
   Under load that ties up a pooled DB connection for as long as the
   provider takes to respond — a slow/degraded provider then degrades
   your own DB connection pool too. Here: commit the reservation, THEN
   call the provider with no open transaction, THEN commit the outcome.
2. Every failure path refunds through the same method
   (`_fail_and_refund`), so "did we refund" is answered by reading one
   function, not by auditing every except-block in every route handler.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GenerationStatus, GenerationType, ModerationVerdict
from app.core.exceptions import (
    ConcurrencyLimitExceededError,
    ContentModerationError,
    GenerationsDisabledError,
    InvalidGenerationParamsError,
    ProviderSubmissionError,
)
from app.core.logging import get_logger
from app.events.bus import dispatch
from app.events.generation import GenerationSubmissionFailed, GenerationSubmitted
from app.mappers.generation import to_response
from app.models.generation import Generation
from app.repository.generations import GenerationRepository
from app.schemas.generation import GenerationResponse
from app.services.credits.service import CreditService
from app.services.generation import pricing
from app.services.moderation.service import moderation_service
from app.services.providers.base import ProviderSubmission
from app.services.providers.fal.catalog import get_model
from app.services.providers.fal.mapper import build_arguments
from app.services.providers.registry import get_provider
from app.services.storage.s3 import presign_download
from app.core.config import settings

logger = get_logger(__name__)


def _model_specific_validation(model_id: str, generation_type: str, duration_seconds: int | None) -> None:
    if generation_type not in (GenerationType.TEXT_TO_VIDEO, GenerationType.IMAGE_TO_VIDEO):
        return
    if duration_seconds and duration_seconds > settings.max_video_duration_seconds:
        raise InvalidGenerationParamsError(
            f"duration_seconds cannot exceed {settings.max_video_duration_seconds}",
            details={"max_duration_seconds": settings.max_video_duration_seconds},
        )
    if model_id == "wan-2.5" and duration_seconds not in (None, 5, 10):
        raise InvalidGenerationParamsError("Wan 2.5 supports 5s or 10s outputs only")
    if model_id.startswith("kling-2.5") and duration_seconds is not None and not 5 <= duration_seconds <= 15:
        raise InvalidGenerationParamsError("Kling 2.5 supports video durations from 5s to 15s")


class GenerationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.generations = GenerationRepository(session)
        self.credits = CreditService(session)

    async def get_owned(self, generation_id: str, user_id: str) -> GenerationResponse:
        row = await self.generations.get_owned(generation_id, user_id)
        if not row:
            from app.core.exceptions import GenerationNotFoundError
            raise GenerationNotFoundError("Generation not found", details={"generation_id": generation_id})
        return to_response(row)

    async def list_for_user(self, user_id: str, *, limit: int = 50, offset: int = 0) -> list[GenerationResponse]:
        rows = await self.generations.list_for_user(user_id, limit=limit, offset=offset)
        return [to_response(r) for r in rows]

    async def rename(self, generation_id: str, user_id: str, title: str) -> GenerationResponse:
        row = await self.generations.rename(generation_id, user_id, title)
        if not row:
            from app.core.exceptions import GenerationNotFoundError
            raise GenerationNotFoundError("Generation not found", details={"generation_id": generation_id})
        await self.session.commit()
        return to_response(row)

    async def create(
        self,
        *,
        user_id: str,
        generation_type: str,
        model_id: str,
        prompt: str | None = None,
        input_s3_key: str | None = None,
        secondary_input_s3_key: str | None = None,
        duration_seconds: int | None = None,
        resolution: str | None = None,
        aspect_ratio: str | None = None,
        num_images: int = 1,
        target_language: str | None = None,
        idempotency_key: str | None = None,
        project_id: str | None = None,
        shot_id: str | None = None,
        character_id: str | None = None,
        reservation_safety_margin: float = 1.0,
    ) -> GenerationResponse:
        if not settings.generations_enabled:
            raise GenerationsDisabledError("Generation is temporarily disabled")

        if idempotency_key:
            existing = await self.generations.get_by_idempotency_key(user_id, idempotency_key)
            if existing:
                return to_response(existing)

        moderation = moderation_service.check_prompt(prompt)
        if moderation.verdict == ModerationVerdict.BLOCK:
            raise ContentModerationError("This request was rejected by content moderation", details={"reasons": moderation.reasons})

        model = get_model(model_id)
        if model["type"] != generation_type:
            raise InvalidGenerationParamsError(
                f"Model {model_id} does not support {generation_type}",
                details={"model_id": model_id, "requested_type": generation_type},
            )
        _model_specific_validation(model_id, generation_type, duration_seconds)

        active_count = await self.generations.count_active_for_user(user_id)
        if active_count >= settings.max_concurrent_generations_per_user:
            raise ConcurrencyLimitExceededError(
                f"You have {active_count} generations already in progress",
                details={"limit": settings.max_concurrent_generations_per_user},
            )

        cost_usd, credits = pricing.estimate_reservation(
            model, duration_seconds=duration_seconds, num_images=num_images, safety_margin=reservation_safety_margin
        )

        generation_id = "gen_" + uuid4().hex
        row = Generation(
            id=generation_id, user_id=user_id, type=generation_type, status=GenerationStatus.RESERVING_CREDITS,
            model_id=model_id, prompt=prompt, input_s3_key=input_s3_key, secondary_input_s3_key=secondary_input_s3_key,
            resolution=resolution, aspect_ratio=aspect_ratio, duration_seconds=duration_seconds,
            estimated_provider_cost_usd=Decimal(str(cost_usd)), credits_reserved=credits,
            idempotency_key=idempotency_key, project_id=project_id, shot_id=shot_id, character_id=character_id,
            moderation_verdict=moderation.verdict,
        )
        self.generations.add(row)
        await self.credits.reserve(user_id, generation_id, credits, f"Reserved for {model['name']} ({generation_type})")
        await self.session.commit()  # transaction A ends here — no open transaction during the provider call below

        try:
            submission = await self._submit_to_provider(
                model=model, generation_type=generation_type, prompt=prompt, input_s3_key=input_s3_key,
                secondary_input_s3_key=secondary_input_s3_key, duration_seconds=duration_seconds,
                resolution=resolution, aspect_ratio=aspect_ratio, num_images=num_images, target_language=target_language,
            )
        except Exception as exc:  # noqa: BLE001 - any provider failure must refund
            await self._fail_and_refund(generation_id, user_id, credits, "PROVIDER_SUBMIT_FAILED", str(exc))
            raise

        row = await self.generations.get_for_update(generation_id)
        row.provider_request_id = submission.provider_request_id
        row.status = GenerationStatus.PROCESSING
        row.started_at = datetime.now(timezone.utc)
        await self.session.commit()

        dispatch(GenerationSubmitted.now(
            generation_id=generation_id, user_id=user_id, generation_type=generation_type,
            model_id=model_id, credits_reserved=credits,
        ))
        logger.info("generation_submitted", generation_id=generation_id, type=generation_type, model=model_id, credits=credits)
        return to_response(row)

    async def _submit_to_provider(
        self, *, model: dict, generation_type: str, prompt: str | None, input_s3_key: str | None,
        secondary_input_s3_key: str | None, duration_seconds: int | None, resolution: str | None,
        aspect_ratio: str | None, num_images: int, target_language: str | None,
    ) -> ProviderSubmission:
        provider = get_provider()
        provider_model_id, _args = build_arguments(
            model["id"], generation_type, prompt=prompt,
            input_url=presign_download(input_s3_key) if input_s3_key else None,
            secondary_input_url=presign_download(secondary_input_s3_key) if secondary_input_s3_key else None,
            duration_seconds=duration_seconds, resolution=resolution, aspect_ratio=aspect_ratio,
            num_images=num_images, target_language=target_language,
        )
        image_url = presign_download(input_s3_key) if input_s3_key else None
        audio_url = presign_download(secondary_input_s3_key) if secondary_input_s3_key else None

        if generation_type == GenerationType.TEXT_TO_IMAGE:
            return await provider.submit_text_to_image(provider_model_id, prompt, num_images=num_images, aspect_ratio=aspect_ratio)
        if generation_type == GenerationType.IMAGE_TO_IMAGE:
            return await provider.submit_image_to_image(provider_model_id, prompt, image_url)
        if generation_type == GenerationType.TEXT_TO_VIDEO:
            return await provider.submit_text_to_video(provider_model_id, prompt, duration=str(duration_seconds or 5), resolution=resolution or "720p", aspect_ratio=aspect_ratio or "16:9")
        if generation_type == GenerationType.IMAGE_TO_VIDEO:
            return await provider.submit_image_to_video(provider_model_id, prompt, image_url, duration=str(duration_seconds or 5), resolution=resolution or "720p")
        if generation_type == GenerationType.AVATAR:
            return await provider.submit_avatar(provider_model_id, image_url, audio_url)
        if generation_type == GenerationType.VIDEO_TRANSLATION:
            return await provider.submit_video_translation(provider_model_id, image_url, target_language or "en")
        if generation_type == GenerationType.AUDIO_REPLACE:
            return await provider.submit_audio_replace(provider_model_id, image_url, audio_url)
        raise InvalidGenerationParamsError(f"Unsupported generation type: {generation_type}")

    async def _fail_and_refund(self, generation_id: str, user_id: str, credits: int, error_code: str, error_message: str) -> None:
        await self.session.rollback()
        row = await self.generations.get_for_update(generation_id)
        if not row or row.status == GenerationStatus.COMPLETED:
            return
        await self.credits.refund(user_id, generation_id, credits, f"Refund: {error_code}")
        row.status = GenerationStatus.REFUNDED
        row.error_code = error_code
        row.error_message = error_message[:2000]
        row.failed_at = datetime.now(timezone.utc)
        await self.session.commit()
        dispatch(GenerationSubmissionFailed.now(
            generation_id=generation_id, user_id=user_id, error_code=error_code, credits_refunded=credits,
        ))
        logger.warning("generation_submission_failed", generation_id=generation_id, error_code=error_code)
