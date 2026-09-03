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
"""
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.constants import GenerationStatus
from app.core.database import system_session
from app.core.logging import get_logger
from app.events.bus import dispatch
from app.events.generation import GenerationCompleted, GenerationFailed
from app.models.generation import Generation
from app.repository.generations import GenerationRepository
from app.services.credits.service import CreditService
from app.services.media.ffmpeg import generate_thumbnail
from app.services.storage.s3 import upload_from_path

logger = get_logger(__name__)


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

                key = f"{row.id}.{'mp4' if is_video else 'png'}"
                output_key = f"{settings.s3_output_prefix}/{row.user_id}/{key}"
                upload_from_path(str(local_media), output_key, content_type)
                row.output_s3_key = output_key

                if is_video:
                    thumb_path = Path(tmpdir) / "thumb.jpg"
                    try:
                        await generate_thumbnail(str(local_media), str(thumb_path))
                        thumb_key = f"{output_key}.thumb.jpg"
                        upload_from_path(str(thumb_path), thumb_key, "image/jpeg")
                        row.thumbnail_s3_key = thumb_key
                    except Exception as exc:  # noqa: BLE001 - a missing thumbnail must not fail the whole generation
                        logger.warning("thumbnail_generation_failed", generation_id=generation_id, error=str(exc))

            row.status = GenerationStatus.COMPLETED
            row.credits_charged = row.credits_reserved
            row.completed_at = datetime.now(timezone.utc)
            await session.commit()
            dispatch(GenerationCompleted.now(generation_id=row.id, user_id=row.user_id, credits_charged=row.credits_charged))
            logger.info("generation_finalized", generation_id=generation_id)

            if row.shot_id and row.project_id:
                await _mark_shot_completed_and_maybe_assemble(session, row.project_id, row.shot_id)

        except Exception as exc:  # noqa: BLE001 - any finalize failure must refund
            await session.rollback()
            await _fail_and_refund(session, generation_id, "MEDIA_FINALIZATION_FAILED", str(exc))


async def _mark_shot_completed_and_maybe_assemble(session, project_id: str, shot_id: str) -> None:
    """Movie feature hook: a shot's underlying Generation just completed —
    flip the Shot to completed and, if it was the last one in the Project,
    kick off movie assembly. Imported lazily to avoid a circular import
    (services.movie.service imports GenerationService, which lives next to
    this module)."""
    from app.core.constants import ShotStatus
    from app.models.project import Shot
    from app.services.movie.service import MovieService

    shot = await session.get(Shot, shot_id)
    if shot:
        shot.status = ShotStatus.COMPLETED
        await session.commit()

    await MovieService(session).maybe_assemble(project_id)


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
    dispatch(GenerationFailed.now(generation_id=row.id, user_id=row.user_id, error_code=error_code, credits_refunded=row.credits_reserved))
    logger.warning("generation_finalize_failed", generation_id=generation_id, error_code=error_code)

    if row.shot_id:
        from app.core.constants import ShotStatus
        from app.models.project import Shot
        shot = await session.get(Shot, row.shot_id)
        if shot:
            shot.status = ShotStatus.FAILED
            await session.commit()
