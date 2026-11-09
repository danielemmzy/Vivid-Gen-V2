"""FinalizeGenerationJob — what happens after the provider webhook confirms
a generation succeeded: download the output, move it into our own S3
bucket (never serve directly from the provider's temporary URL — those
expire and we lose the asset), generate a thumbnail for video, mark the
generation completed, and charge the reserved credits. On any failure here,
refund and mark failed — this is the second half of the reserve/charge
pattern that GenerationService starts.

This module defines *what* runs; workers/worker.py defines *how* (ARQ
config, concurrency, retries) — see the architecture plan's jobs vs.
workers split.

gap-closure (0007): a shot's Generation completing/failing now notifies
orchestration/scheduler.py's on_task_completed for that shot's SCENE task
— the real DAG's execution authority — instead of round 2's flat
`production_task.mark_scene_task_for_shot` + `MovieService.maybe_assemble`
(both deleted this round). Also records ProductionBudgetService charges/
refunds and updates the latest GenerationAttempt row (additive audit
history — see models/generation_attempt.py)."""
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.constants import GenerationAttemptStatus, GenerationStatus
from app.core.database import system_session
from app.core.logging import get_logger
from app.events.bus import dispatch
from app.events.generation import GenerationCompleted, GenerationFailed
from app.models.generation import Generation
from app.repository.generations import GenerationRepository
from app.services.credits.service import CreditService
from app.services.generation.pricing import calculate_credits, estimate_reservation
from app.services.media.ffmpeg import generate_thumbnail, probe_duration_seconds, resize_video_to_output_resolution
from app.services.providers.fal.catalog import get_model
from app.services.storage.s3 import upload_from_path

logger = get_logger(__name__)


async def submit_generation(ctx, generation_id: str) -> None:
    """Worker-side provider submission. Kept separate from finalization so
    provider calls are retried/observed independently from media processing."""
    from app.services.generation.service import GenerationService
    async with system_session() as session:
        await GenerationService(session).submit_queued(generation_id)


async def finalize_generation(ctx, generation_id: str) -> None:
    async with system_session() as session:
        repo = GenerationRepository(session)
        row = await repo.get_for_update(generation_id)
        if not row or row.status == GenerationStatus.COMPLETED:
            return

        output_url = (row.metadata_json or {}).get("provider_output_url")
        content_type = (row.metadata_json or {}).get("provider_content_type") or (
            "video/mp4" if "video" in row.type or row.type in ("avatar", "video_translation", "audio_replace") else "image/png"
        )
        if not output_url:
            logger.error("finalize_missing_output_url", generation_id=generation_id)
            return

        is_video = content_type.startswith("video/")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                local_media = Path(tmpdir) / ("clip.mp4" if is_video else "image.png")
                await _download(output_url, str(local_media))

                # `resolution` on text/image-to-video generations is the final
                # output target (420p/720p), not a provider generation knob.
                # Normalize after provider output so the selectable setting is
                # true in the delivered file even for provider-native models.
                if is_video and row.type in ("text_to_video", "image_to_video") and row.resolution in ("420p", "720p"):
                    normalized_media = Path(tmpdir) / "normalized.mp4"
                    await resize_video_to_output_resolution(
                        str(local_media), str(normalized_media), resolution=row.resolution,
                    )
                    if normalized_media.exists():
                        local_media = normalized_media

                key = f"{row.id}.{'mp4' if is_video else 'png'}"
                output_key = f"{settings.s3_output_prefix}/{row.user_id}/{key}"
                upload_from_path(str(local_media), output_key, content_type)
                row.output_s3_key = output_key

                actual_duration_seconds: float | None = None
                if is_video:
                    thumb_path = Path(tmpdir) / "thumb.jpg"
                    try:
                        await generate_thumbnail(str(local_media), str(thumb_path))
                        thumb_key = f"{output_key}.thumb.jpg"
                        upload_from_path(str(thumb_path), thumb_key, "image/jpeg")
                        row.thumbnail_s3_key = thumb_key
                    except Exception as exc:  # noqa: BLE001 - a missing thumbnail must not fail the whole generation
                        logger.warning("thumbnail_generation_failed", generation_id=generation_id, error=str(exc))
                    try:
                        actual_duration_seconds = await probe_duration_seconds(str(local_media))
                    except Exception as exc:  # noqa: BLE001 - reconciliation is best-effort, never blocks finalize
                        logger.warning("duration_probe_failed", generation_id=generation_id, error=str(exc))

            # Billing reconciliation (round 2): recompute the true cost
            # from the actual duration when it came in shorter than what
            # was reserved for, refunding the rest. Never charges MORE
            # than was reserved, regardless of what the probe says.
            row.credits_charged = row.credits_reserved
            # Provider APIs currently do not send invoice-confirmed per-call
            # costs. Track the successful attempt's best available estimate,
            # plus any failed-attempt runtime estimates, and label provenance.
            failed_attempt_cost = float((row.metadata_json or {}).get("failed_attempt_cost_estimate_usd_total", 0) or 0)
            final_cost_source = "catalog_estimate"
            final_attempt_cost = float(row.estimated_provider_cost_usd or 0)
            runtime_cost = (row.metadata_json or {}).get("provider_runtime_cost_estimate_usd")
            runtime_cost_source = (row.metadata_json or {}).get("provider_cost_source")
            if runtime_cost is not None and runtime_cost_source == "modal_runtime_estimate":
                final_attempt_cost = float(runtime_cost)
                final_cost_source = "modal_runtime_estimate"
            row.actual_provider_cost_usd = round(final_attempt_cost + failed_attempt_cost, 8)
            row.actual_cost_source = "mixed_estimates" if failed_attempt_cost > 0 else final_cost_source
            refund_amount = 0
            if actual_duration_seconds is not None and actual_duration_seconds > 0:
                try:
                    model = get_model(row.model_id)
                    # Runtime-based Modal costs are already estimated from
                    # the actual function runtime and must not be overwritten
                    # by an output-duration-only catalog calculation.
                    if final_cost_source == "modal_runtime_estimate":
                        actual_cost_usd = final_attempt_cost
                        actual_credits = calculate_credits(
                            actual_cost_usd, markup_multiplier=model.get("retail_multiplier")
                        )
                    else:
                        actual_cost_usd, actual_credits = estimate_reservation(model, duration_seconds=actual_duration_seconds, safety_margin=1.0)
                        final_attempt_cost = actual_cost_usd
                    row.actual_provider_cost_usd = round(final_attempt_cost + failed_attempt_cost, 8)
                    row.actual_cost_source = "mixed_estimates" if failed_attempt_cost > 0 else final_cost_source
                    if actual_credits > row.credits_reserved:
                        row.metadata_json = {
                            **(row.metadata_json or {}),
                            "billing_reconciliation": {
                                "status": "under_reserved",
                                "estimated_actual_credits": actual_credits,
                                "credits_charged": row.credits_reserved,
                                "uncovered_credits": actual_credits - row.credits_reserved,
                                "cost_source": row.actual_cost_source,
                            },
                        }
                    if actual_credits < row.credits_reserved:
                        refund_amount = row.credits_reserved - actual_credits
                        row.metadata_json = {
                            **(row.metadata_json or {}),
                            "billing_reconciliation": {
                                "status": "reconciled_refund",
                                "estimated_actual_credits": actual_credits,
                                "credits_charged": actual_credits,
                                "credits_refunded": refund_amount,
                                "cost_source": row.actual_cost_source,
                            },
                        }
                        row.credits_charged = actual_credits
                        row.actual_provider_cost_usd = round(final_attempt_cost + failed_attempt_cost, 8)
                        row.actual_cost_source = "mixed_estimates" if failed_attempt_cost > 0 else final_cost_source
                except Exception as exc:  # noqa: BLE001 - reconciliation is best-effort; fall back to full charge rather than fail finalize
                    logger.warning("billing_reconciliation_failed", generation_id=generation_id, error=str(exc))

            row.status = GenerationStatus.COMPLETED
            row.completed_at = datetime.now(timezone.utc)
            await session.commit()

            await _mark_latest_attempt(
                session, row, status=GenerationAttemptStatus.SUCCEEDED,
                actual_cost_usd=float(final_attempt_cost),
                actual_cost_source=final_cost_source,
            )

            if refund_amount > 0:
                await CreditService(session).refund(row.user_id, row.id, refund_amount, "Billing reconciliation: actual cost lower than reserved estimate")
                await session.commit()
                logger.info("generation_billing_reconciled", generation_id=generation_id, refunded=refund_amount)

            if row.production_id:
                from app.services.production.budget_service import ProductionBudgetService
                await ProductionBudgetService(session).record_charge(row.production_id, generation_id=row.id, amount=row.credits_charged)
                if refund_amount > 0:
                    await ProductionBudgetService(session).record_refund(row.production_id, generation_id=row.id, amount=refund_amount)

            dispatch(GenerationCompleted.now(generation_id=row.id, user_id=row.user_id, credits_charged=row.credits_charged))
            logger.info("generation_finalized", generation_id=generation_id)

            if row.shot_id and row.project_id:
                await _mark_shot_completed_and_notify_scheduler(session, row.project_id, row.shot_id)

        except Exception as exc:  # noqa: BLE001 - any finalize failure must refund
            await session.rollback()
            await _fail_and_refund(session, generation_id, "MEDIA_FINALIZATION_FAILED", str(exc))


async def _mark_shot_completed_and_notify_scheduler(session, project_id: str, shot_id: str) -> None:
    """gap-closure (0007): replaces round 2's
    `_mark_shot_completed_and_maybe_assemble` — a shot's Generation
    completing now notifies the real DAG scheduler for that shot's SCENE
    task (orchestration/scheduler.py::on_task_completed), which is what
    atomically evaluates VOICE/RENDER's readiness and enqueues them if
    they just became READY. `MovieService.maybe_assemble` (the old flat
    "last shot done -> assemble" trigger) no longer exists — this IS the
    trigger now, and it goes through the DAG, not a shot-count check."""
    from app.core.constants import ShotStatus
    from app.models.project import Shot
    from app.orchestration import dag, scheduler

    shot = await session.get(Shot, shot_id)
    if shot:
        shot.status = ShotStatus.COMPLETED
        await session.commit()

    task = await dag.get_task_for_shot(session, shot_id)
    if task:
        from app.core.constants import ProductionTaskStatus
        task.status = ProductionTaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await scheduler.on_task_completed(session, task.id, success=True)


async def _mark_latest_attempt(session, generation: Generation, *, status: str, actual_cost_usd: float | None = None, actual_cost_source: str | None = None, error: str | None = None, failure_type: str | None = None) -> None:
    """gap-closure (0007): GenerationAttempt is additive audit history —
    services/generation/service.py creates one row per submission try;
    this updates the most recent one's outcome once it's known (finalize
    success/failure), rather than duplicating attempt-creation logic
    here."""
    from sqlalchemy import select
    from app.models.generation_attempt import GenerationAttempt

    attempt = (
        await session.execute(
            select(GenerationAttempt).where(GenerationAttempt.generation_id == generation.id)
            .order_by(GenerationAttempt.attempt_number.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if not attempt:
        return
    attempt.status = status
    attempt.completed_at = datetime.now(timezone.utc)
    if actual_cost_usd is not None:
        attempt.actual_cost_usd = actual_cost_usd
    if actual_cost_source is not None:
        attempt.actual_cost_source = actual_cost_source
    if error:
        attempt.error = error[:2000]
    if failure_type:
        attempt.failure_type = failure_type
    await session.commit()


async def _download(url: str, local_path: str) -> None:
    if url.startswith("file://"):
        # Used only by the fake provider's local fixtures (see
        # providers/fake/client.py) — no network call, works fully offline.
        import shutil
        shutil.copyfile(url[len("file://"):], local_path)
        return
    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(local_path, "wb") as f:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    f.write(chunk)


async def _fail_and_refund(session, generation_id: str, error_code: str, error_message: str) -> None:
    repo = GenerationRepository(session)
    row = await repo.get_for_update(generation_id)
    if not row or row.status in (GenerationStatus.COMPLETED, GenerationStatus.REFUNDED):
        return
    credits_service = CreditService(session)
    await credits_service.refund(row.user_id, row.id, row.credits_reserved, f"Refund: {error_code}")
    row.status = GenerationStatus.REFUNDED
    row.error_code = error_code
    row.error_message = error_message[:2000]
    row.failed_at = datetime.now(timezone.utc)
    await session.commit()

    await _mark_latest_attempt(session, row, status=GenerationAttemptStatus.FAILED, error=error_message, failure_type="finalization_failed")

    if row.production_id:
        from app.services.production.budget_service import ProductionBudgetService
        await ProductionBudgetService(session).record_refund(row.production_id, generation_id=row.id, amount=row.credits_reserved)

    dispatch(GenerationFailed.now(generation_id=row.id, user_id=row.user_id, error_code=error_code, credits_refunded=row.credits_reserved))
    logger.warning("generation_finalize_failed", generation_id=generation_id, error_code=error_code)

    if row.shot_id:
        from app.core.constants import ProductionTaskStatus, ShotStatus
        from app.models.project import Shot
        from app.orchestration import dag, scheduler
        shot = await session.get(Shot, row.shot_id)
        if shot:
            shot.status = ShotStatus.FAILED
            await session.commit()
        task = await dag.get_task_for_shot(session, row.shot_id)
        # Same guard as MovieService._submit_generation_for — a
        # regenerate_shot call on an already-completed (rendered) shot
        # must not retroactively fail a task that already succeeded and
        # potentially already unlocked downstream work.
        if task and task.status != ProductionTaskStatus.COMPLETED:
            task.status = ProductionTaskStatus.FAILED
            task.error = error_message[:2000]
            task.completed_at = datetime.now(timezone.utc)
            await session.commit()
            await scheduler.on_task_completed(session, task.id, success=False, error=error_message[:2000])
