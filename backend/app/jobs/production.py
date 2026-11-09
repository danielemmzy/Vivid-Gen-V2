"""gap-closure (0007): the ARQ job functions the DAG scheduler
(orchestration/scheduler.py) actually dispatches to. Each function here
is one ProductionTaskType's executor — this is the "for task in tasks:
enqueue(task)" replaced with real per-type behavior, called only when
the scheduler decides a task is READY, never as a flat loop over
"every task".

Every job function follows the same shape:
    1. load the task; if it's not RUNNING (already completed/cancelled
       by a race — e.g. the whole production was cancelled between
       enqueue and this job actually starting), no-op.
    2. do the work, writing `task.output_json`.
    3. set task.status to COMPLETED/FAILED/SKIPPED and call
       orchestration.scheduler.on_task_completed — that's what unlocks
       whatever's downstream.

SCENE tasks are the one exception: `run_scene_task` only SUBMITS the
generation (synchronous provider call) and returns — the task stays
RUNNING until the async provider webhook completes it via
jobs/generation.py's `_mark_shot_completed_and_notify_scheduler`/
`_fail_and_refund`, which call `on_task_completed` themselves. Every
other task type here does its work synchronously within the job and
calls `on_task_completed` directly at the end.
"""
import tempfile
from datetime import datetime, timezone

from app.core.constants import ProductionTaskStatus, ProductionTaskType
from app.core.database import system_session
from app.core.logging import get_logger
from app.models.production import Production
from app.models.production_task import ProductionTask
from app.orchestration import dag, render_manifest_builder, scheduler
from app.services.media.ffmpeg import FfmpegError
from app.services.media.renderer import render as render_manifest_to_file

logger = get_logger(__name__)


async def _load_running_task(session, task_id: str) -> ProductionTask | None:
    task = await session.get(ProductionTask, task_id)
    if not task:
        logger.error("task_missing", task_id=task_id)
        return None
    if task.status != ProductionTaskStatus.RUNNING:
        # Cancelled/already-handled by a race — see module docstring.
        logger.info("task_skip_not_running", task_id=task_id, status=task.status)
        return None
    return task


async def run_scene_task(ctx, task_id: str) -> None:
    """Submits the Shot's generation. Does NOT mark the task COMPLETED
    itself — that happens asynchronously when the provider webhook fires
    (see jobs/generation.py). Only handles the SYNCHRONOUS submission
    failure path (every retry/fallback exhausted before a
    provider_request_id was even obtained) — MovieService._submit_generation_for
    already calls scheduler.on_task_completed(success=False) in that
    case, so nothing further is needed here."""
    async with system_session() as session:
        task = await _load_running_task(session, task_id)
        if not task or not task.shot_id:
            return
        from app.models.project import Shot
        from app.services.movie.service import MovieService

        shot = await session.get(Shot, task.shot_id)
        if not shot:
            logger.error("run_scene_task_missing_shot", task_id=task_id)
            return
        production = await session.get(Production, task.production_id)
        try:
            await MovieService(session)._submit_generation_for(production.user_id, shot.project_id, shot)
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - already handled (task failed + scheduler notified) inside _submit_generation_for
            logger.warning("run_scene_task_submission_failed", task_id=task_id, error=str(exc))


async def run_voice_task(ctx, task_id: str) -> None:
    async with system_session() as session:
        task = await _load_running_task(session, task_id)
        if not task:
            return
        production = await session.get(Production, task.production_id)
        plan, brand_kit = await render_manifest_builder.load_plan_and_brand_kit(session, production)
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                output = await render_manifest_builder.synthesize_voice_segments(session, production, plan, brand_kit, tmpdir)
            except Exception as exc:  # noqa: BLE001 - explicitly requested narration must not silently disappear
                logger.warning("run_voice_task_failed", task_id=task_id, error=str(exc))
                task.output_json = {"error": str(exc)[:500], "segments": []}
                task.status = ProductionTaskStatus.FAILED if plan.voiceover.enabled else ProductionTaskStatus.SKIPPED
                task.completed_at = datetime.now(timezone.utc)
                await session.commit()
                await scheduler.on_task_completed(session, task_id, success=task.status != ProductionTaskStatus.FAILED)
                return

        task.output_json = output
        task.status = ProductionTaskStatus.COMPLETED if output.get("segments") else ProductionTaskStatus.SKIPPED
        task.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await scheduler.on_task_completed(session, task_id, success=True)


async def run_captions_task(ctx, task_id: str) -> None:
    async with system_session() as session:
        task = await _load_running_task(session, task_id)
        if not task:
            return
        production = await session.get(Production, task.production_id)
        voice_task = await dag.get_task_by_type(session, production.id, ProductionTaskType.VOICE)
        voice_output = voice_task.output_json if voice_task and voice_task.output_json else {"segments": []}

        output = None
        if voice_output.get("segments"):
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    output = await render_manifest_builder.transcribe_captions(session, production, voice_output, tmpdir)
                except Exception as exc:  # noqa: BLE001 - captions are optional polish
                    logger.warning("run_captions_task_failed", task_id=task_id, error=str(exc))

        task.output_json = output
        task.status = ProductionTaskStatus.COMPLETED if output else ProductionTaskStatus.SKIPPED
        task.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await scheduler.on_task_completed(session, task_id, success=True)


async def run_music_task(ctx, task_id: str) -> None:
    async with system_session() as session:
        task = await _load_running_task(session, task_id)
        if not task:
            return
        production = await session.get(Production, task.production_id)
        plan, brand_kit = await render_manifest_builder.load_plan_and_brand_kit(session, production)
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                output = await render_manifest_builder.resolve_music(session, production, plan, brand_kit, tmpdir)
            except Exception as exc:  # noqa: BLE001 - requested music/ambience must not silently disappear
                logger.warning("run_music_task_failed", task_id=task_id, error=str(exc))
                task.output_json = {"error": str(exc)[:500], "tracks": []}
                requested = plan.music.enabled or plan.ambience.enabled
                task.status = ProductionTaskStatus.FAILED if requested else ProductionTaskStatus.SKIPPED
                task.completed_at = datetime.now(timezone.utc)
                await session.commit()
                await scheduler.on_task_completed(session, task_id, success=not requested)
                return

        task.output_json = output
        task.status = ProductionTaskStatus.COMPLETED if output.get("tracks") else ProductionTaskStatus.SKIPPED
        task.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await scheduler.on_task_completed(session, task_id, success=True)


async def run_branding_task(ctx, task_id: str) -> None:
    async with system_session() as session:
        task = await _load_running_task(session, task_id)
        if not task:
            return
        production = await session.get(Production, task.production_id)
        _plan, brand_kit = await render_manifest_builder.load_plan_and_brand_kit(session, production)
        try:
            output = await render_manifest_builder.resolve_branding(session, production, brand_kit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("run_branding_task_failed", task_id=task_id, error=str(exc))
            output = None

        task.output_json = output
        task.status = ProductionTaskStatus.COMPLETED if output else ProductionTaskStatus.SKIPPED
        task.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await scheduler.on_task_completed(session, task_id, success=True)


async def run_render_task(ctx, task_id: str) -> None:
    """The sink. Only ever enqueued once every SCENE/VOICE/CAPTIONS/
    MUSIC/BRANDING task for this production is COMPLETED or SKIPPED —
    the scheduler guarantees that, not this function. Builds the
    RenderManifest purely from its dependencies' already-written
    output_json (render_manifest_builder.assemble_manifest_from_tasks),
    renders it (the same services/media/renderer.py canonical path
    rounds 1-2 established), and finalizes the Production on success."""
    from uuid import uuid4
    from app.core.constants import ProductionStatus, ProjectStatus, RenderJobStatus
    from app.models.asset import Asset
    from app.models.project import Project
    from app.models.render_job import RenderJob
    from app.orchestration.production_plan import ProductionPlan
    from app.orchestration.executor import load_plan_record

    async with system_session() as session:
        task = await _load_running_task(session, task_id)
        if not task:
            return
        production = await session.get(Production, task.production_id)
        project = await session.get(Project, production.project_id)
        plan_record = await load_plan_record(session, production.id)
        plan = ProductionPlan.model_validate(plan_record.plan_json)

        render_job = RenderJob(
            id="rjob_" + uuid4().hex, project_id=project.id, production_id=production.id, user_id=production.user_id,
            status=RenderJobStatus.PREPARING, attempt=1, started_at=datetime.now(timezone.utc),
        )
        session.add(render_job)
        task.render_job_id = render_job.id
        project.status = ProjectStatus.ASSEMBLING
        await session.commit()

        try:
            manifest = await render_manifest_builder.assemble_manifest_from_tasks(session, production, plan)
            if not manifest.video_tracks:
                raise FfmpegError("No scene produced a completed clip to render")

            render_job.manifest_json = manifest.model_dump(mode="json")
            render_job.status = RenderJobStatus.RENDERING
            render_job.current_step = "rendering"
            render_job.progress_percent = 40
            await session.commit()

            output_key = await render_manifest_to_file(manifest)

            output_asset = Asset(
                id="asset_" + uuid4().hex, project_id=project.id, user_id=production.user_id, type="video",
                source="render", s3_key=output_key, asset_metadata={"kind": "master", "production_id": production.id},
            )
            session.add(output_asset)
            await session.flush()

            project.output_s3_key = output_key
            project.output_duration_seconds = (
                manifest.target_duration_seconds
                if manifest.target_duration_seconds is not None
                else sum(float(track.duration_seconds or 0.0) for track in manifest.video_tracks)
            )
            project.status = ProjectStatus.READY
            project.completed_at = datetime.now(timezone.utc)
            render_job.status = RenderJobStatus.COMPLETED
            render_job.progress_percent = 100
            render_job.current_step = "completed"
            render_job.output_asset_id = output_asset.id
            render_job.completed_at = datetime.now(timezone.utc)

            task.output_json = {"render_job_id": render_job.id, "output_asset_id": output_asset.id}
            task.status = ProductionTaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)

            production.status = ProductionStatus.COMPLETED
            production.execution_status = ProductionStatus.COMPLETED
            production.completed_at = datetime.now(timezone.utc)
            await session.commit()

            from app.services.production.budget_service import ProductionBudgetService
            await ProductionBudgetService(session).reconcile_on_completion(production.id)

            logger.info("production_render_completed", production_id=production.id, render_job_id=render_job.id)
            await scheduler.on_task_completed(session, task_id, success=True)
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            project = await session.get(Project, production.project_id)
            project.status = ProjectStatus.FAILED
            project.error_message = str(exc)[:2000]
            render_job = await session.get(RenderJob, render_job.id)
            if render_job:
                render_job.status = RenderJobStatus.FAILED
                render_job.error = str(exc)[:2000]
                render_job.completed_at = datetime.now(timezone.utc)
            task = await session.get(ProductionTask, task_id)
            task.status = ProductionTaskStatus.FAILED
            task.error = str(exc)[:2000]
            task.completed_at = datetime.now(timezone.utc)
            await session.commit()
            logger.error("production_render_failed", production_id=production.id, error=str(exc))
            await scheduler.on_task_completed(session, task_id, success=False, error=str(exc)[:2000])
