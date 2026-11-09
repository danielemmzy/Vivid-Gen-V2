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
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GenerationAttemptStatus, GenerationStatus, GenerationType, ModerationVerdict, ProviderErrorClass
from app.core.exceptions import (
    ConcurrencyLimitExceededError,
    ContentModerationError,
    GenerationNotCancellableError,
    GenerationsDisabledError,
    InvalidGenerationParamsError,
    ProviderSubmissionError,
)
from app.core.logging import get_logger
from app.events.bus import dispatch
from app.events.generation import GenerationSubmissionFailed, GenerationSubmitted
from app.mappers.generation import to_response
from app.models.generation import Generation
from app.models.generation_attempt import GenerationAttempt
from app.orchestration.model_router import RoutingRequest, select_with_fallback
from app.orchestration.provider_errors import classify_error, classify_exception
from app.repository.generations import GenerationRepository
from app.schemas.generation import GenerationResponse
from app.services.credits.service import CreditService
from app.services.generation import pricing
from app.services.moderation.service import moderation_service
from app.services.providers.base import ProviderSubmission
from app.services.providers.fal.catalog import get_model
from app.services.providers.fal.mapper import build_arguments
from app.services.providers.registry import get_provider, provider_is_configured
from app.services.storage.s3 import presign_download
from app.core.config import settings

logger = get_logger(__name__)


def _model_specific_validation(
    model_id: str, generation_type: str, duration_seconds: int | None,
    resolution: str | None = None, aspect_ratio: str | None = None,
    *, has_image_input: bool = False, has_audio_input: bool = False,
) -> None:
    """Backward-compatible wrapper around the shared capability contract."""
    from app.services.generation.capabilities import validate_generation_request
    validate_generation_request(
        get_model(model_id), generation_type=generation_type,
        duration_seconds=duration_seconds, resolution=resolution,
        aspect_ratio=aspect_ratio, has_image_input=has_image_input,
        has_audio_input=has_audio_input,
    )


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

    async def _record_attempt(
        self, *, generation_id: str, production_id: str | None, production_task_id: str | None, user_id: str,
        provider: str | None, model_id: str | None, status: str, estimated_cost_usd: float | None = None,
        actual_cost_usd: float | None = None, failure_type: str | None = None, error: str | None = None,
    ) -> GenerationAttempt:
        """gap-closure (0007): GenerationAttempt — additive per-attempt
        audit history alongside `Generation.retry_count`/
        `attempted_model_ids` (unchanged, still the authoritative
        retry-loop counters — see module docstring's design note). One
        row per submission try, including fallback resubmissions."""
        from sqlalchemy import select
        count = (
            await self.session.execute(select(GenerationAttempt).where(GenerationAttempt.generation_id == generation_id))
        ).scalars().all()
        attempt = GenerationAttempt(
            id="gattempt_" + uuid4().hex, generation_id=generation_id, production_id=production_id,
            production_task_id=production_task_id, user_id=user_id, attempt_number=len(count) + 1,
            provider=provider, model_id=model_id, status=status, estimated_cost_usd=estimated_cost_usd,
            actual_cost_usd=actual_cost_usd, failure_type=failure_type, error=error[:2000] if error else None,
        )
        if status != GenerationAttemptStatus.SUBMITTED:
            attempt.completed_at = datetime.now(timezone.utc)
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def create(
        self,
        *,
        user_id: str,
        generation_type: str,
        model_id: str | None = None,
        quality_mode: str = "medium",
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
        production_id: str | None = None,
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

        if model_id:
            model = get_model(model_id)
            if not model.get("enabled", True):
                raise InvalidGenerationParamsError(
                    f"Model {model_id} is disabled",
                    details={"model_id": model_id, "reason": "model_disabled"},
                )
            if model["type"] != generation_type:
                raise InvalidGenerationParamsError(
                    f"Model {model_id} does not support {generation_type}",
                    details={"model_id": model_id, "requested_type": generation_type},
                )
            effective_provider = "fake" if settings.generation_provider == "fake" else model.get("provider", settings.generation_provider)
            if not provider_is_configured(effective_provider):
                raise InvalidGenerationParamsError(
                    f"Provider '{effective_provider}' is not configured",
                    details={"model_id": model_id, "provider": effective_provider, "reason": "provider_not_configured"},
                )
        else:
            model = await select_with_fallback(self.session, RoutingRequest(
                capability=generation_type, quality_mode=quality_mode,
                duration_seconds=duration_seconds,
            ), max_attempts=1)
            if not model:
                raise InvalidGenerationParamsError(
                    f"No configured model is available for {generation_type} at quality '{quality_mode}'",
                    details={"generation_type": generation_type, "quality_mode": quality_mode},
                )
            model = model[0]
            model_id = model["id"]
        if generation_type in (GenerationType.TEXT_TO_VIDEO, GenerationType.IMAGE_TO_VIDEO) and resolution is None:
            from app.services.generation.capabilities import get_capabilities
            supported = get_capabilities(model).get("resolutions", [])
            resolution = "720p" if "720p" in supported else (supported[0] if supported else None)
        _model_specific_validation(
            model_id, generation_type, duration_seconds, resolution, aspect_ratio,
            has_image_input=bool(input_s3_key) and generation_type in (GenerationType.IMAGE_TO_IMAGE, GenerationType.IMAGE_TO_VIDEO, GenerationType.AVATAR),
            has_audio_input=bool(secondary_input_s3_key) and generation_type in (GenerationType.AVATAR, GenerationType.AUDIO_REPLACE),
        )

        # Browser media metadata is useful for the pre-generation quote, but it
        # is user-controlled and cannot be trusted for credit reservations.
        # Verify duration from the private S3 object before reserving credits.
        if generation_type in (GenerationType.AVATAR, GenerationType.VIDEO_TRANSLATION, GenerationType.AUDIO_REPLACE):
            duration_key = secondary_input_s3_key if generation_type == GenerationType.AVATAR else input_s3_key
            if not duration_key:
                raise InvalidGenerationParamsError(
                    "A source audio/video asset is required to estimate duration safely",
                    details={"generation_type": generation_type, "reason": "duration_source_missing"},
                )
            try:
                from app.services.media.ffmpeg import probe_duration_seconds
                duration_url = await asyncio.to_thread(presign_download, duration_key)
                verified_duration = ceil(await probe_duration_seconds(duration_url))
            except Exception as exc:  # noqa: BLE001 - do not reserve using unverified client metadata
                raise InvalidGenerationParamsError(
                    "Vivid Gen could not verify the source media duration. Please re-upload the file and try again.",
                    details={"generation_type": generation_type, "reason": "duration_probe_failed"},
                ) from exc
            if verified_duration < 1 or verified_duration > 900:
                raise InvalidGenerationParamsError(
                    "Source media must be between 1 second and 15 minutes for this operation",
                    details={"verified_duration_seconds": verified_duration, "max_duration_seconds": 900},
                )
            if duration_seconds is not None and abs(int(duration_seconds) - verified_duration) > 2:
                raise InvalidGenerationParamsError(
                    "The source duration changed since the estimate. Refresh the estimate and try again.",
                    details={"estimated_duration_seconds": int(duration_seconds), "verified_duration_seconds": verified_duration},
                )
            duration_seconds = verified_duration

        if generation_type in (GenerationType.TEXT_TO_VIDEO, GenerationType.IMAGE_TO_VIDEO, GenerationType.VIDEO_TRANSLATION, GenerationType.AUDIO_REPLACE):
            from app.services.entitlements import enforce_generation_entitlement
            await enforce_generation_entitlement(self.session, user_id, duration_seconds)

        active_count = await self.generations.count_active_for_user(user_id)
        if active_count >= settings.max_concurrent_generations_per_user:
            raise ConcurrencyLimitExceededError(
                f"You have {active_count} generations already in progress",
                details={"limit": settings.max_concurrent_generations_per_user},
            )

        # Unknown-length media must not reserve as though it were a one-second
        # job. Use explicit conservative defaults until source duration is
        # supplied/probed; finalization reconciles against the rendered output.
        pricing_duration_seconds = duration_seconds
        if pricing_duration_seconds is None and generation_type == GenerationType.AVATAR:
            pricing_duration_seconds = settings.avatar_reservation_seconds
        elif pricing_duration_seconds is None and generation_type in (GenerationType.VIDEO_TRANSLATION, GenerationType.AUDIO_REPLACE):
            pricing_duration_seconds = settings.unknown_media_reservation_seconds
        reservation_cost_usd, credits = pricing.estimate_reservation(
            model, duration_seconds=pricing_duration_seconds, num_images=num_images,
            safety_margin=reservation_safety_margin,
        )
        provider_cost_estimate_usd = pricing.provider_cost_usd(
            model, duration_seconds=pricing_duration_seconds, num_images=num_images,
        )

        generation_id = "gen_" + uuid4().hex
        row = Generation(
            id=generation_id, user_id=user_id, type=generation_type, status=GenerationStatus.RESERVING_CREDITS,
            model_id=model_id, prompt=prompt, input_s3_key=input_s3_key, secondary_input_s3_key=secondary_input_s3_key,
            resolution=resolution, aspect_ratio=aspect_ratio, duration_seconds=duration_seconds,
            estimated_provider_cost_usd=Decimal(str(provider_cost_estimate_usd)), credits_reserved=credits,
            idempotency_key=idempotency_key, project_id=project_id, shot_id=shot_id, production_id=production_id, character_id=character_id,
            moderation_verdict=moderation.verdict,
        )
        self.generations.add(row)
        await self.credits.reserve(user_id, generation_id, credits, f"Reserved for {model['name']} ({generation_type})")
        try:
            await self.session.commit()  # transaction A ends here — no open transaction during the provider call below
        except IntegrityError:
            # Two concurrent requests with the same idempotency_key both
            # passed the check above before either committed — a genuine
            # race, not a bug in the check itself (the DB's unique index
            # on (user_id, idempotency_key) is the actual safety net, this
            # is just making losing that race return the winner's row
            # instead of a raw 500). Roll back this attempt entirely
            # (generation row + credit reservation both undone, same
            # transaction) and return whichever request won.
            await self.session.rollback()
            if idempotency_key:
                existing = await self.generations.get_by_idempotency_key(user_id, idempotency_key)
                if existing:
                    return to_response(existing)
            raise

        # Provider submission is deliberately asynchronous. The durable ARQ job
        # is the hand-off point between API traffic and external GPU/provider
        # capacity; the provider webhook remains the completion signal.
        row.status = GenerationStatus.QUEUED
        row.metadata_json = {
            **(row.metadata_json or {}),
            "num_images": num_images,
            "target_language": target_language,
            "quality_mode": quality_mode,
            "capabilities_snapshot": model.get("capabilities"),
            "pricing_snapshot": {
                "provider": model.get("provider"),
                "provider_model_id": model.get("provider_model_id"),
                "estimated_provider_cost_usd": float(provider_cost_estimate_usd),
                "estimated_reservation_cost_usd": float(reservation_cost_usd),
                "reservation_safety_margin": reservation_safety_margin,
                "cost_strategy": model.get("cost_strategy", "catalog_unit_price"),
                "cost_estimate_basis": model.get("cost_estimate_basis", "catalog price snapshot"),
                "modal_cost_rate_version": settings.modal_cost_rate_version if model.get("provider") == "modal" else None,
                "reservation_duration_seconds": pricing_duration_seconds,
            },
        }
        await self.session.commit()
        try:
            from app.jobs.queue import enqueue_generation_submission
            await enqueue_generation_submission(generation_id)
        except Exception as exc:  # noqa: BLE001
            await self._fail_and_refund(
                generation_id, user_id, credits, "GENERATION_QUEUE_FAILED", str(exc),
            )
            raise ProviderSubmissionError(
                "Generation queue is temporarily unavailable",
                details={"generation_id": generation_id},
            ) from exc
        logger.info("generation_queued", generation_id=generation_id, type=generation_type, model=model_id, credits=credits)
        return to_response(row)

    async def submit_queued(self, generation_id: str) -> None:
        """Submit a reserved generation from the durable ARQ queue.

        The API transaction only reserves credits and creates the generation.
        Network/provider calls happen in a worker so slow Fal/Modal submissions
        cannot consume API event-loop capacity or hold database connections.
        """
        row = await self.generations.get_for_update(generation_id)
        if not row or row.status != GenerationStatus.QUEUED or row.provider_request_id:
            return
        model = get_model(row.model_id)
        generation_type = row.type
        duration_seconds = int(row.duration_seconds) if row.duration_seconds is not None else None
        resolution = row.resolution
        aspect_ratio = row.aspect_ratio
        num_images = int((row.metadata_json or {}).get("num_images", 1))
        target_language = (row.metadata_json or {}).get("target_language")
        pricing_duration_seconds = duration_seconds
        if pricing_duration_seconds is None:
            pricing_duration_seconds = ((row.metadata_json or {}).get("pricing_snapshot") or {}).get("reservation_duration_seconds")

        # Preserve the original quality preference for provider retries.
        # This method runs in the queue worker, so quality_mode must be
        # restored from the generation's saved metadata.
        quality_mode = (row.metadata_json or {}).get("quality_mode", "medium")

        prompt = row.prompt
        input_s3_key = row.input_s3_key
        secondary_input_s3_key = row.secondary_input_s3_key
        credits = int(row.credits_reserved)
        user_id = row.user_id
        await self.session.commit()

        # Previously any exception here immediately refunded and raised —
        # model_router.select_with_fallback existed but nothing ever
        # called it. Now a TRANSIENT failure (per provider_errors.py)
        # retries against the next capability-matching model before
        # giving up; a PERMANENT failure still fails on the first attempt,
        # since retrying it would only waste the provider call.
        attempted_model_ids = [row.model_id]
        current_model = model
        submission: ProviderSubmission | None = None
        last_error_message = ""
        require_movie_shot_support = row.shot_id is not None

        production_task_id = None
        if row.shot_id:
            from app.orchestration import dag
            task = await dag.get_task_for_shot(self.session, row.shot_id)
            production_task_id = task.id if task else None

        for attempt in range(settings.max_generation_retry_attempts):
            attempt_cost_usd, _attempt_credits = pricing.estimate_reservation(
                current_model, duration_seconds=pricing_duration_seconds, num_images=num_images,
            )
            try:
                submission = await self._submit_to_provider(
                    model=current_model, generation_type=generation_type, prompt=prompt, input_s3_key=input_s3_key,
                    secondary_input_s3_key=secondary_input_s3_key, duration_seconds=duration_seconds,
                    resolution=resolution, aspect_ratio=aspect_ratio, num_images=num_images, target_language=target_language,
                )
                await self._record_attempt(
                    generation_id=generation_id, production_id=row.production_id, production_task_id=production_task_id,
                    user_id=user_id, provider=current_model.get("provider"), model_id=current_model["id"],
                    status=GenerationAttemptStatus.SUCCEEDED, estimated_cost_usd=float(attempt_cost_usd),
                )
                break
            except Exception as exc:  # noqa: BLE001 - classified below, not blindly swallowed
                last_error_message = str(exc)
                error_class = classify_exception(exc)
                is_last_attempt = attempt == settings.max_generation_retry_attempts - 1
                await self._record_attempt(
                    generation_id=generation_id, production_id=row.production_id, production_task_id=production_task_id,
                    user_id=user_id, provider=current_model.get("provider"), model_id=current_model["id"],
                    status=GenerationAttemptStatus.FAILED, failure_type=error_class, error=last_error_message,
                    estimated_cost_usd=float(attempt_cost_usd),
                )
                logger.warning(
                    "generation_submission_attempt_failed", generation_id=generation_id,
                    model_id=current_model["id"], attempt=attempt + 1, error_class=error_class, error=last_error_message,
                )
                if error_class != ProviderErrorClass.TRANSIENT or is_last_attempt:
                    await self._fail_and_refund(
                        generation_id, user_id, credits, "PROVIDER_SUBMIT_FAILED", last_error_message,
                        retry_count=attempt + 1, attempted_model_ids=attempted_model_ids,
                    )
                    # gap-closure (0006): attach the generation_id to the
                    # exception itself so a caller like
                    # MovieService._submit_generation_for can still link
                    # the Shot to the (refunded) Generation for
                    # traceability, even though the call failed.
                    exc.generation_id = generation_id
                    raise
                # select_with_fallback never raises (it internally catches
                # NoRoutableModelError and returns whatever chain it has,
                # possibly empty) — check for an empty chain, not a raise.
                chain = await select_with_fallback(self.session, RoutingRequest(
                    capability=generation_type, quality_mode=quality_mode,
                    exclude_model_ids=tuple(attempted_model_ids),
                    require_movie_shot_support=require_movie_shot_support,
                    duration_seconds=duration_seconds,
                ))
                if not chain:
                    await self._fail_and_refund(
                        generation_id, user_id, credits, "PROVIDER_SUBMIT_FAILED", last_error_message,
                        retry_count=attempt + 1, attempted_model_ids=attempted_model_ids,
                    )
                    exc.generation_id = generation_id
                    raise
                candidate = None
                candidate_cost = None
                candidate_credits = None
                for potential in chain:
                    from app.services.generation.capabilities import fallback_preserves_framing
                    if not fallback_preserves_framing(
                        current_model, potential, generation_type=generation_type, aspect_ratio=aspect_ratio,
                    ):
                        continue
                    try:
                        _model_specific_validation(
                            potential["id"], generation_type, duration_seconds, resolution, aspect_ratio,
                            has_image_input=bool(input_s3_key) and generation_type in (GenerationType.IMAGE_TO_IMAGE, GenerationType.IMAGE_TO_VIDEO, GenerationType.AVATAR),
                            has_audio_input=bool(secondary_input_s3_key) and generation_type in (GenerationType.AVATAR, GenerationType.AUDIO_REPLACE),
                        )
                    except InvalidGenerationParamsError:
                        continue
                    potential_cost, potential_credits = pricing.estimate_reservation(
                        potential, duration_seconds=pricing_duration_seconds, num_images=num_images, safety_margin=1.0
                    )
                    if potential_credits <= credits:
                        candidate, candidate_cost, candidate_credits = potential, potential_cost, potential_credits
                        break
                if candidate is None:
                    await self._fail_and_refund(
                        generation_id, user_id, credits, "PROVIDER_SUBMIT_FAILED",
                        "No fallback model supports the requested capabilities within the reserved credit budget",
                        retry_count=attempt + 1, attempted_model_ids=attempted_model_ids,
                    )
                    exc.generation_id = generation_id
                    raise
                current_model = candidate
                attempted_model_ids.append(current_model["id"])

        assert submission is not None  # loop only exits via `break` (success) or `raise` (exhausted)

        assert submission is not None

        row = await self.generations.get_for_update(generation_id)
        if not row or row.status != GenerationStatus.QUEUED:
            return
        if current_model["id"] != row.model_id:
            selected_cost, _selected_credits = pricing.estimate_reservation(
                current_model, duration_seconds=pricing_duration_seconds, num_images=num_images,
            )
            row.estimated_provider_cost_usd = Decimal(str(selected_cost))
            row.metadata_json = {
                **(row.metadata_json or {}),
                "capabilities_snapshot": current_model.get("capabilities"),
                "pricing_snapshot": {
                    "provider": current_model.get("provider"),
                    "provider_model_id": current_model.get("provider_model_id"),
                    "estimated_provider_cost_usd": float(selected_cost),
                    "cost_strategy": current_model.get("cost_strategy", "catalog_unit_price"),
                    "cost_estimate_basis": current_model.get("cost_estimate_basis", "catalog price snapshot"),
                },
            }
        row.model_id = current_model["id"]
        row.provider_request_id = submission.provider_request_id
        row.status = GenerationStatus.PROCESSING
        row.started_at = datetime.now(timezone.utc)
        row.retry_count = len(attempted_model_ids) - 1
        row.attempted_model_ids = attempted_model_ids
        await self.session.commit()
        dispatch(GenerationSubmitted.now(
            generation_id=generation_id, user_id=user_id, generation_type=generation_type,
            model_id=current_model["id"], credits_reserved=credits,
        ))
        logger.info(
            "generation_submitted", generation_id=generation_id, type=generation_type,
            model=current_model["id"], credits=credits, retry_count=row.retry_count,
        )

    async def handle_provider_error(self, row: Generation, *, error_message: str, status_code: int | None = None) -> None:
        """Called from the fal webhook handler (webhooks/fal.py) when a
        provider reports ERROR for a generation that already has a
        provider_request_id — i.e. an async failure, as opposed to the
        synchronous submission-time failures `create()` handles itself
        above. Same transient/permanent decision, applied after the fact:
        resubmit against the next fallback model, or refund. Caller
        (webhook handler) owns the transaction and commits afterward —
        this method only mutates `row` and calls CreditService, matching
        every other method's caller-commits convention in this file."""
        error_class = classify_error(error_message, status_code=status_code)
        # Close the current attempt with whatever cost telemetry the provider
        # supplied before a fallback is queued or credits are refunded. This
        # keeps failed paid calls visible in the attempt audit trail.
        from sqlalchemy import select
        latest_attempt = (
            await self.session.execute(
                select(GenerationAttempt).where(GenerationAttempt.generation_id == row.id)
                .order_by(GenerationAttempt.attempt_number.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if latest_attempt and latest_attempt.model_id == row.model_id:
            metadata = row.metadata_json or {}
            runtime_cost = metadata.get("provider_runtime_cost_estimate_usd")
            latest_attempt.status = GenerationAttemptStatus.FAILED
            latest_attempt.error = error_message[:2000]
            latest_attempt.completed_at = datetime.now(timezone.utc)
            attempt_cost = runtime_cost if runtime_cost is not None else latest_attempt.estimated_cost_usd
            attempt_cost_source = metadata.get("provider_cost_source", "modal_runtime_estimate") if runtime_cost is not None else "catalog_estimate"
            if attempt_cost is not None:
                row.metadata_json = dict(row.metadata_json or {})
                latest_attempt.actual_cost_usd = attempt_cost
                latest_attempt.actual_cost_source = attempt_cost_source
                prior_failed_cost = float(metadata.get("failed_attempt_cost_estimate_usd_total", 0) or 0)
                failed_total = prior_failed_cost + float(attempt_cost)
                row.metadata_json["failed_attempt_cost_estimate_usd_total"] = round(failed_total, 8)
                row.metadata_json["failed_attempt_cost_sources"] = [
                    *(metadata.get("failed_attempt_cost_sources") or []),
                    {"model_id": row.model_id, "source": attempt_cost_source, "estimated_cost_usd": round(float(attempt_cost), 8)},
                ]
                row.actual_provider_cost_usd = round(failed_total, 8)
                row.actual_cost_source = attempt_cost_source if prior_failed_cost == 0 else "mixed_estimates"
            latest_attempt.response_metadata = {
                **(latest_attempt.response_metadata or {}),
                **{key: metadata[key] for key in ("runtime_seconds", "gpu_seconds", "model_load_seconds", "inference_seconds", "provider_runtime_cost_estimate_usd", "provider_cost_source", "modal_cost_rate_version") if key in metadata},
            }
            # Do not let the failed provider's cost telemetry be attributed to
            # a later fallback provider's output. The failed attempt retains it.
            row.metadata_json = dict(row.metadata_json or {})
            for key in ("runtime_seconds", "gpu_seconds", "model_load_seconds", "inference_seconds", "provider_runtime_cost_estimate_usd", "provider_cost_source", "modal_cost_rate_version"):
                row.metadata_json.pop(key, None)
        attempted = list(row.attempted_model_ids or [row.model_id])
        can_retry = (
            error_class == ProviderErrorClass.TRANSIENT
            and row.retry_count < settings.max_generation_retry_attempts - 1
        )

        next_model = None
        fallback_cost = None
        if can_retry:
            chain = await select_with_fallback(self.session, RoutingRequest(
                capability=row.type, exclude_model_ids=tuple(attempted), require_movie_shot_support=bool(row.shot_id),
                duration_seconds=float(row.duration_seconds) if row.duration_seconds is not None else None,
            ))
            reservation_duration = row.duration_seconds
            if reservation_duration is None:
                reservation_duration = ((row.metadata_json or {}).get("pricing_snapshot") or {}).get("reservation_duration_seconds")
            for potential in chain:
                from app.services.generation.capabilities import fallback_preserves_framing
                if not fallback_preserves_framing(
                    get_model(row.model_id), potential, generation_type=row.type, aspect_ratio=row.aspect_ratio,
                ):
                    continue
                try:
                    _model_specific_validation(
                        potential["id"], row.type,
                        float(row.duration_seconds) if row.duration_seconds is not None else None,
                        row.resolution, row.aspect_ratio,
                        has_image_input=bool(row.input_s3_key) and row.type in (GenerationType.IMAGE_TO_IMAGE, GenerationType.IMAGE_TO_VIDEO, GenerationType.AVATAR),
                        has_audio_input=bool(row.secondary_input_s3_key) and row.type in (GenerationType.AVATAR, GenerationType.AUDIO_REPLACE),
                    )
                except InvalidGenerationParamsError:
                    continue
                potential_cost, potential_credits = pricing.estimate_reservation(
                    potential, duration_seconds=float(reservation_duration) if reservation_duration is not None else None,
                    num_images=1,
                )
                if potential_credits <= int(row.credits_reserved):
                    next_model, fallback_cost = potential, potential_cost
                    break

        production_task_id = None
        if row.shot_id:
            from app.orchestration import dag
            task = await dag.get_task_for_shot(self.session, row.shot_id)
            production_task_id = task.id if task else None

        if next_model:
            try:
                submission = await self._submit_to_provider(
                    model=next_model, generation_type=row.type, prompt=row.prompt,
                    input_s3_key=row.input_s3_key, secondary_input_s3_key=row.secondary_input_s3_key,
                    duration_seconds=float(row.duration_seconds) if row.duration_seconds is not None else None,
                    resolution=row.resolution, aspect_ratio=row.aspect_ratio, num_images=1, target_language=None,
                )
            except Exception as exc:  # noqa: BLE001 - the fallback attempt itself failed; fall through to refund
                logger.warning("generation_fallback_resubmit_failed", generation_id=row.id, model_id=next_model["id"], error=str(exc))
                await self._record_attempt(
                    generation_id=row.id, production_id=row.production_id, production_task_id=production_task_id,
                    user_id=row.user_id, provider=next_model.get("provider"), model_id=next_model["id"],
                    status=GenerationAttemptStatus.FAILED, failure_type=ProviderErrorClass.TRANSIENT, error=str(exc),
                )
            else:
                row.model_id = next_model["id"]
                row.provider_request_id = submission.provider_request_id
                row.retry_count += 1
                row.attempted_model_ids = [*attempted, next_model["id"]]
                row.status = GenerationStatus.PROCESSING
                row.error_code = None
                row.error_message = None
                await self._record_attempt(
                    generation_id=row.id, production_id=row.production_id, production_task_id=production_task_id,
                    user_id=row.user_id, provider=next_model.get("provider"), model_id=next_model["id"],
                    status=GenerationAttemptStatus.SUCCEEDED,
                    estimated_cost_usd=float(fallback_cost or 0),
                )
                row.estimated_provider_cost_usd = Decimal(str(fallback_cost or 0))
                row.metadata_json = {
                    **(row.metadata_json or {}),
                    "capabilities_snapshot": next_model.get("capabilities"),
                    "pricing_snapshot": {
                        "provider": next_model.get("provider"),
                        "provider_model_id": next_model.get("provider_model_id"),
                        "estimated_provider_cost_usd": float(fallback_cost or 0),
                        "cost_strategy": next_model.get("cost_strategy", "catalog_unit_price"),
                        "cost_estimate_basis": next_model.get("cost_estimate_basis", "catalog price snapshot"),
                    },
                }
                logger.warning(
                    "generation_fallback_resubmitted", generation_id=row.id,
                    model_id=next_model["id"], retry_count=row.retry_count,
                )
                return

        # No transient retry available (permanent error, retries exhausted,
        # or the fallback submission itself raised) — refund, same
        # end-state as the pre-audit code, but now the reason is recorded.
        await self.credits.refund(row.user_id, row.id, row.credits_reserved, f"Refund: provider error ({error_class})")
        row.status = GenerationStatus.REFUNDED
        row.error_code = "FAL_GENERATION_FAILED" if not can_retry and error_class == ProviderErrorClass.PERMANENT else "FAL_GENERATION_FAILED_RETRIES_EXHAUSTED"
        row.error_message = error_message[:2000]
        row.failed_at = datetime.now(timezone.utc)
        if row.production_id:
            from app.services.production.budget_service import ProductionBudgetService
            await ProductionBudgetService(self.session).record_refund(row.production_id, generation_id=row.id, amount=row.credits_reserved)
        dispatch(GenerationSubmissionFailed.now(
            generation_id=row.id, user_id=row.user_id, error_code=row.error_code, credits_refunded=row.credits_reserved,
        ))
        logger.warning("generation_failed_after_retries", generation_id=row.id, error_class=error_class, retry_count=row.retry_count)

    async def cancel(self, generation_id: str, user_id: str) -> GenerationResponse:
        """gap-closure: there was previously no way to cancel a generation
        anywhere in the API — ProjectStatus.CANCELLED existed as a legal
        state-machine transition but nothing ever produced it. Only
        cancellable while still in a refundable, non-terminal state; we
        don't attempt to cancel the request on the provider's side (no
        provider in this codebase exposes a cancel API), we just stop
        waiting on it and refund — a late webhook for an already-cancelled
        generation is a no-op (see webhooks/fal.py's terminal-state check,
        which now includes CANCELLED)."""
        from app.core.exceptions import GenerationNotFoundError

        row = await self.generations.get_for_update(generation_id)
        if not row or row.user_id != user_id:
            raise GenerationNotFoundError("Generation not found", details={"generation_id": generation_id})
        if GenerationStatus(row.status).is_terminal:
            raise GenerationNotCancellableError(
                "This generation has already finished and can no longer be cancelled",
                details={"generation_id": generation_id, "status": row.status},
            )
        await self.credits.refund(user_id, generation_id, row.credits_reserved - row.credits_charged, "Cancelled by user")
        row.status = GenerationStatus.CANCELLED
        row.error_code = "CANCELLED_BY_USER"
        row.failed_at = datetime.now(timezone.utc)
        await self.session.commit()
        if row.production_id:
            from app.services.production.budget_service import ProductionBudgetService
            await ProductionBudgetService(self.session).record_refund(row.production_id, generation_id=row.id, amount=row.credits_reserved - row.credits_charged)
        if row.shot_id:
            from app.core.constants import ProductionTaskStatus
            from app.orchestration import dag, scheduler
            task = await dag.get_task_for_shot(self.session, row.shot_id)
            if task and not ProductionTaskStatus(task.status).is_terminal:
                task.status = ProductionTaskStatus.FAILED
                task.error = "Generation cancelled by user"
                task.completed_at = datetime.now(timezone.utc)
                await self.session.commit()
                await scheduler.on_task_completed(self.session, task.id, success=False, error=task.error)
        logger.info("generation_cancelled", generation_id=generation_id, user_id=user_id)
        return to_response(row)

    async def _submit_to_provider(
        self, *, model: dict, generation_type: str, prompt: str | None, input_s3_key: str | None,
        secondary_input_s3_key: str | None, duration_seconds: int | None, resolution: str | None,
        aspect_ratio: str | None, num_images: int, target_language: str | None,
    ) -> ProviderSubmission:
        # Per-model provider routing (V2 Phase 2) — each catalog entry now
        # names its own provider (fal, modal, ...). `GENERATION_PROVIDER`
        # stays a blanket override, not just a per-model fallback: when
        # it's explicitly set to "fake" (local dev/testing — see
        # providers/fake/client.py), that always wins over whatever the
        # model says, otherwise every catalog entry saying "fal" would
        # silently defeat fake-mode testing. Outside of "fake", the
        # model's own provider is used, falling back to the global
        # setting only for a model with no provider set at all.
        provider_name = "fake" if settings.generation_provider == "fake" else (model.get("provider") or settings.generation_provider)
        provider = get_provider(provider_name)
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
            return await provider.submit_text_to_image(provider_model_id, prompt, **_args)
        if generation_type == GenerationType.IMAGE_TO_IMAGE:
            return await provider.submit_image_to_image(provider_model_id, prompt, image_url, **_args)
        if generation_type == GenerationType.TEXT_TO_VIDEO:
            return await provider.submit_text_to_video(provider_model_id, prompt, **_args)
        if generation_type == GenerationType.IMAGE_TO_VIDEO:
            return await provider.submit_image_to_video(provider_model_id, prompt, image_url, **_args)
        if generation_type == GenerationType.AVATAR:
            return await provider.submit_avatar(provider_model_id, image_url, audio_url)
        if generation_type == GenerationType.VIDEO_TRANSLATION:
            return await provider.submit_video_translation(provider_model_id, image_url, target_language or "en")
        if generation_type == GenerationType.AUDIO_REPLACE:
            return await provider.submit_audio_replace(provider_model_id, image_url, audio_url)
        raise InvalidGenerationParamsError(f"Unsupported generation type: {generation_type}")

    async def _fail_and_refund(
        self, generation_id: str, user_id: str, credits: int, error_code: str, error_message: str,
        *, retry_count: int | None = None, attempted_model_ids: list[str] | None = None,
    ) -> None:
        await self.session.rollback()
        row = await self.generations.get_for_update(generation_id)
        if not row or row.status == GenerationStatus.COMPLETED:
            return
        await self.credits.refund(user_id, generation_id, credits, f"Refund: {error_code}")
        row.status = GenerationStatus.REFUNDED
        row.error_code = error_code
        row.error_message = error_message[:2000]
        row.failed_at = datetime.now(timezone.utc)
        # retry bookkeeping must be set here, after the rollback above,
        # not by the caller beforehand — an uncommitted assignment made
        # before this method's own rollback() would otherwise be lost.
        if retry_count is not None:
            row.retry_count = retry_count
        if attempted_model_ids is not None:
            row.attempted_model_ids = attempted_model_ids
        await self.session.commit()
        if row.production_id:
            from app.services.production.budget_service import ProductionBudgetService
            await ProductionBudgetService(self.session).record_refund(row.production_id, generation_id=row.id, amount=credits)
        dispatch(GenerationSubmissionFailed.now(
            generation_id=generation_id, user_id=user_id, error_code=error_code, credits_refunded=credits,
        ))
        logger.warning("generation_submission_failed", generation_id=generation_id, error_code=error_code)
