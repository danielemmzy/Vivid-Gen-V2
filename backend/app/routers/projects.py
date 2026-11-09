"""The movie/storyboard feature's API surface: create a project, add
characters (reference sheets for identity consistency), add shots, submit
shots for generation, and check assembly status. See
services/movie/service.py for the orchestration this delegates to.

V2 additions (plan / approve-plan / generate): the AI Director surface.
POST /plan calls the LLM and stores a ProductionPlan without spending any
credits or creating any Shots — round 3 (gap-closure) also creates the
first-class Production this now always goes through (see models/
production.py). POST /approve-plan turns that plan (or an edited version
of it the caller submits) into real Shot rows AND the real dependency DAG
(orchestration/dag.py) — still no credits spent, nothing enqueued.
POST /generate is the one that actually spends credits: it reserves the
ProductionBudget and starts the DAG scheduler (orchestration/scheduler.py),
which enqueues whichever tasks are currently ready and lets task
completion drive everything downstream from there — it does NOT
synchronously submit every shot itself the way it did before round 3.
This three-step split exists specifically so a user can see and edit a
plan before anything costs money (spec §16, §53)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone
from typing import Any, Literal

from app.core.constants import ProjectStatus, ProductionStatus, ProductionTaskStatus, ProductionTaskType
from app.core.exceptions import PlanValidationError, ProjectNotFoundError
from app.dependencies import current_user_id, db_session
from app.models.production import Production
from app.models.project import Project
from app.orchestration import dag, executor, scheduler
from app.orchestration.plan_validator import validate_plan
from app.orchestration.planner import create_production_plan
from app.orchestration.production_plan import ProductionPlan
from app.orchestration.scheduler import start_production
from app.services.movie.service import MovieService
from app.services.production.budget_service import ProductionBudgetService
from app.services.storage.s3 import presign_download

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"


class CreateCharacterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    reference_s3_keys: list[str] = Field(min_length=1, max_length=6)
    voice_id: str | None = None


class AddShotRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    camera_notes: str | None = Field(default=None, max_length=500)
    duration_seconds: int = Field(default=5, ge=3, le=15)
    character_ids: list[str] = Field(default_factory=list, max_length=4)
    model_id: str | None = None


class CreatePlanRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    project_type: str = "video"
    duration_seconds: int | None = Field(default=None, ge=5, le=600)
    aspect_ratio: str | None = None
    resolution: str | None = Field(default=None, pattern=r"^(420p|720p|1080p|1440p)$")
    quality_mode: Literal["low", "medium", "high", "fast", "balanced", "best"] | None = None
    model_id: str | None = None
    target_platform: str | None = None
    style: str | None = None
    audience: str | None = None
    language: str = "en"
    source_facts: str | None = Field(default=None, max_length=20000)


class ApprovePlanRequest(BaseModel):
    # Lets the frontend's plan-review screen submit a user-edited plan
    # (spec §53). If omitted, the plan already stored from POST /plan is
    # used unchanged.
    plan: ProductionPlan | None = None


def _project_dict(project) -> dict:
    return {
        "id": project.id, "title": project.title, "description": project.description, "status": project.status,
        "aspect_ratio": project.aspect_ratio, "resolution": project.resolution,
        "output_url": presign_download(project.output_s3_key) if project.output_s3_key else None,
        "error_message": project.error_message,
        "production_plan": (project.metadata_json or {}).get("production_plan"),
        "editor_timeline": (project.metadata_json or {}).get("editor_timeline"),
        "preview_started": bool((project.metadata_json or {}).get("preview_started", False)),
        "current_production_id": project.current_production_id,
    }


def _shot_dict(shot) -> dict:
    return {
        "id": shot.id, "order_index": shot.order_index, "scene_number": shot.scene_number, "status": shot.status, "prompt": shot.prompt,
        "camera_notes": shot.camera_notes, "duration_seconds": shot.duration_seconds,
        "character_ids": shot.character_ids, "generation_id": shot.generation_id,
        "generation_history": shot.generation_history,  # V2 (B08): past generation_ids, oldest first
        "reference_shot_id": shot.reference_shot_id,
        "product_id": shot.product_id,
        "continuity_mode": shot.continuity_mode,
        "timeline_duration_seconds": float(shot.timeline_duration_seconds) if shot.timeline_duration_seconds is not None else None,
    }


def _character_dict(character) -> dict:
    return {
        "id": character.id, "name": character.name, "locked_version": character.locked_version,
        "reference_urls": [presign_download(k) for k in character.reference_s3_keys],
        "voice_id": character.voice_id,
    }


async def _get_owned_or_404(session: AsyncSession, project_id: str, user_id: str):
    project = await MovieService(session).repo.get_owned(project_id, user_id)
    if not project:
        raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
    return project


@router.post("")
async def create_project(body: CreateProjectRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    project = await MovieService(session).create_project(user_id, body.title, body.description, body.aspect_ratio, body.resolution)
    return _project_dict(project)


@router.post("/{project_id}/characters")
async def create_character(project_id: str, body: CreateCharacterRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    character = await MovieService(session).create_character(user_id, project_id, body.name, body.description, body.reference_s3_keys, body.voice_id)
    return _character_dict(character)


@router.post("/{project_id}/shots")
async def add_shot(project_id: str, body: AddShotRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    shot = await MovieService(session).add_shot(
        user_id, project_id, prompt=body.prompt, camera_notes=body.camera_notes,
        duration_seconds=body.duration_seconds, character_ids=body.character_ids, model_id=body.model_id,
    )
    return _shot_dict(shot)


class EditorTimelineRequest(BaseModel):
    timeline: dict[str, Any]


@router.put("/{project_id}/editor-timeline")
async def save_editor_timeline(
    project_id: str, body: EditorTimelineRequest,
    user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
):
    """Persist user-owned editor state without changing generation or credit state.

    The editor schema is versioned and bounded so this JSON field cannot be used
    as an unbounded asset upload. Render integration consumes this state in a
    later stage; saving it does not claim to have rendered those edits.
    """
    import json
    from fastapi import HTTPException

    project = await _get_owned_or_404(session, project_id, user_id)
    timeline = body.timeline
    if timeline.get("version") != 1:
        raise HTTPException(status_code=422, detail="Unsupported editor timeline version")
    if not isinstance(timeline.get("clips", []), list) or len(timeline.get("clips", [])) > 300:
        raise HTTPException(status_code=422, detail="Timeline may contain at most 300 clips")
    if not isinstance(timeline.get("textLayers", []), list) or len(timeline.get("textLayers", [])) > 500:
        raise HTTPException(status_code=422, detail="Timeline may contain at most 500 text layers")
    if not isinstance(timeline.get("audioLayers", []), list) or len(timeline.get("audioLayers", [])) > 100:
        raise HTTPException(status_code=422, detail="Timeline may contain at most 100 audio layers")
    try:
        serialized_timeline = json.dumps(timeline, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Editor timeline contains invalid values")
    if len(serialized_timeline) > 500_000:
        raise HTTPException(status_code=413, detail="Editor timeline is too large")
    owned_shots = await MovieService(session).repo.get_shots(project_id)
    owned_shot_map = {shot.id: shot for shot in owned_shots}
    owned_shot_ids = set(owned_shot_map)
    shot_prompts: dict[str, str] = {}
    shot_order: dict[str, int] = {}
    shot_timeline_durations: dict[str, float] = {}
    for clip in timeline.get("clips", []):
        if not isinstance(clip, dict) or not isinstance(clip.get("shotId"), str) or clip.get("shotId") not in owned_shot_ids:
            raise HTTPException(status_code=422, detail="Timeline clip references a shot outside this project")
        prompt = clip.get("prompt", owned_shot_map[clip["shotId"]].prompt)
        if not isinstance(prompt, str) or len(prompt) > 2000:
            raise HTTPException(status_code=422, detail="Clip prompts must be text up to 2000 characters")
        shot_id = clip["shotId"]
        if shot_id in shot_prompts and shot_prompts[shot_id] != prompt:
            raise HTTPException(status_code=422, detail="Clips derived from the same shot must share one generation prompt")
        shot_prompts[shot_id] = prompt
        shot_order.setdefault(shot_id, len(shot_order))
        try:
            duration = float(clip.get("duration", 0))
            trim_start = float(clip.get("trimStart", 0))
            trim_end = float(clip.get("trimEnd", 0))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Timeline clip timing must be numeric")
        if duration <= 0 or duration > 600 or trim_start < 0 or trim_end < 0 or trim_start + trim_end >= duration:
            raise HTTPException(status_code=422, detail="Timeline clip timing is outside the supported range")
        shot_timeline_durations[shot_id] = shot_timeline_durations.get(shot_id, 0.0) + duration - trim_start - trim_end
        try:
            volume = float(clip.get("volume", 100))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Timeline clip volume must be numeric")
        if not 0 <= volume <= 100 or clip.get("transition", "none") not in ("none", "fade", "dissolve", "wipe"):
            raise HTTPException(status_code=422, detail="Timeline clip settings are invalid")
    for layer in timeline.get("textLayers", []):
        if not isinstance(layer, dict) or not isinstance(layer.get("text"), str) or len(layer["text"]) > 500:
            raise HTTPException(status_code=422, detail="Text layers must contain text up to 500 characters")
        if layer.get("style") not in ("title", "caption", "label"):
            raise HTTPException(status_code=422, detail="Text layer style is invalid")
        try:
            start_seconds = float(layer.get("start", 0))
            duration_seconds = float(layer.get("duration", 3))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Text layer timing must be numeric")
        if start_seconds < 0 or start_seconds > 600 or duration_seconds <= 0 or duration_seconds > 600:
            raise HTTPException(status_code=422, detail="Text layer timing is outside the supported range")
    for layer in timeline.get("audioLayers", []):
        if not isinstance(layer, dict) or layer.get("kind") not in ("music", "voice", "sfx"):
            raise HTTPException(status_code=422, detail="Audio layer settings are invalid")
        try:
            start_seconds = float(layer.get("start", 0))
            duration_seconds = float(layer.get("duration", 1))
            volume = float(layer.get("volume", 80))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Audio layer values must be numeric")
        if start_seconds < 0 or start_seconds > 600 or duration_seconds <= 0 or duration_seconds > 600 or not 0 <= volume <= 100:
            raise HTTPException(status_code=422, detail="Audio layer values are outside the supported range")
    aspect_ratio = timeline.get("aspectRatio")
    if aspect_ratio not in ("16:9", "9:16", "1:1", "4:5"):
        raise HTTPException(status_code=422, detail="Unsupported editor aspect ratio")
    metadata = dict(project.metadata_json or {})
    metadata["editor_timeline"] = timeline
    project.metadata_json = metadata
    # Keep scene-level script and sequence data aligned with the editor; clip
    # variants from one shot share one prompt and aggregate timeline duration.
    for shot_id, prompt in shot_prompts.items():
        shot = owned_shot_map[shot_id]
        shot.prompt = prompt
        shot.order_index = shot_order[shot_id]
        shot.timeline_duration_seconds = shot_timeline_durations[shot_id]
    next_order = len(shot_order)
    for shot in sorted(owned_shots, key=lambda item: item.order_index):
        if shot.id not in shot_order:
            shot.order_index = next_order
            next_order += 1
    await session.commit()
    return {"saved": True, "editor_timeline": timeline}


@router.post("/{project_id}/shots/{shot_id}/submit")
async def submit_shot(project_id: str, shot_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    shot = await MovieService(session).submit_shot(user_id, project_id, shot_id)
    return _shot_dict(shot)


class RegenerateShotRequest(BaseModel):
    prompt: str | None = Field(default=None, max_length=2000)


@router.post("/{project_id}/shots/{shot_id}/regenerate")
async def regenerate_shot(project_id: str, shot_id: str, body: RegenerateShotRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """V2 (B08 — scene versioning): creates a new attempt at this shot,
    optionally with an edited prompt, without losing the previous one."""
    shot = await MovieService(session).regenerate_shot(user_id, project_id, shot_id, prompt=body.prompt)
    return _shot_dict(shot)


class SelectShotVersionRequest(BaseModel):
    generation_id: str


@router.post("/{project_id}/shots/{shot_id}/select-version")
async def select_shot_version(project_id: str, shot_id: str, body: SelectShotVersionRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    shot = await MovieService(session).select_shot_version(project_id, shot_id, body.generation_id)
    return _shot_dict(shot)


@router.post("/{project_id}/plan")
async def create_plan(project_id: str, body: CreatePlanRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """Calls the AI Director and stores the resulting plan. Spends no
    credits and creates no Shots — see `approve_plan` for that step.

    gap-closure (0007): also creates the first-class Production this
    project's plan/approve/generate cycle now always has (previously the
    plan lived only in Project.metadata_json with no run object at all
    — see orchestration/executor.py::create_production_for_plan)."""
    project = await _get_owned_or_404(session, project_id, user_id)
    metadata = dict(project.metadata_json or {})
    metadata["preview_started"] = False
    project.metadata_json = metadata
    project.status = ProjectStatus.PLANNING
    await session.commit()
    existing_characters = await MovieService(session).repo.list_characters(project_id)
    plan = await create_production_plan(
        prompt=body.prompt, project_type=body.project_type, duration_seconds=body.duration_seconds,
        aspect_ratio=body.aspect_ratio, target_platform=body.target_platform, style=body.style,
        audience=body.audience, language=body.language, source_facts=body.source_facts,
        existing_characters=[{"id": c.id, "name": c.name} for c in existing_characters],
    )
    # Preserve delivery settings chosen in the creation UI in the persisted editable plan.
    if body.resolution:
        plan.resolution = body.resolution
    if body.quality_mode:
        plan.quality_mode = body.quality_mode
    production = await executor.create_production_for_plan(session, user_id, project, plan, director_input=body.model_dump())
    return {**_project_dict(project), "production_id": production.id}


@router.post("/{project_id}/approve-plan")
async def approve_plan(project_id: str, body: ApprovePlanRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """Turns the (optionally user-edited) plan into real Shot rows AND
    the real DAG (orchestration/dag.py) — SCENE/VOICE/CAPTIONS/MUSIC/
    BRANDING/RENDER tasks with real dependency edges. Still spends no
    credits and enqueues nothing — see `generate_project` for that step.

    gap-closure: previously nothing validated the plan between "Director
    produced it" and "user can approve it" — a plan referencing a
    nonexistent character/brand_kit, or one that was mostly
    stock_video/text_graphic scenes (silently skipped by the executor),
    was approvable with no warning. See orchestration/plan_validator.py."""
    project = await _get_owned_or_404(session, project_id, user_id)
    if body.plan is not None:
        plan = body.plan
    else:
        _production, plan = await executor.load_plan_for_project(session, project)
        if plan is None:
            from app.core.exceptions import InvalidGenerationParamsError
            raise InvalidGenerationParamsError("No plan to approve — call POST /plan first, or include one in this request")

    validation_errors = await validate_plan(session, user_id, project_id, plan)
    if validation_errors:
        raise PlanValidationError("This plan cannot be approved as-is", details={"errors": validation_errors})

    metadata = dict(project.metadata_json or {})
    metadata["preview_started"] = False
    project.metadata_json = metadata
    result = await executor.execute_plan(session, user_id, project, plan)
    return {
        **_project_dict(project),
        "production_id": result.production_id,
        "shots": [_shot_dict(s) for s in result.created_shots],
        "skipped_scenes": result.skipped_scenes,
        "warnings": result.warnings,
    }


@router.post("/{project_id}/generate")
async def generate_project(project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """The credit-spending step. gap-closure (0007): this is now
    literally "Production approved -> DAG initialized -> find root
    tasks -> enqueue READY roots" — reserves the ProductionBudget (the
    real per-generation reservation still happens inside
    GenerationService.create when each SCENE task's job actually
    submits — this is the production-level checkpoint on top of that,
    see services/production/budget_service.py) and calls
    orchestration/scheduler.py::start_production, which is the ONLY
    place a task is ever enqueued without having been triggered by
    another task's completion.

    Previously (rounds 1-2) this endpoint synchronously submitted every
    pending shot itself via asyncio.gather — that direct-submission code
    path is gone; SCENE tasks are submitted by jobs/production.py's
    run_scene_task, dispatched by the scheduler, not by this endpoint.

    Safe to call more than once — start_production only enqueues tasks
    still in `ready` status; a production already running has none."""
    project = await _get_owned_or_404(session, project_id, user_id)
    if not project.current_production_id:
        from app.core.exceptions import InvalidGenerationParamsError
        raise InvalidGenerationParamsError("This project has no approved plan yet — call POST /approve-plan first")

    production = await session.get(Production, project.current_production_id)
    if ProductionStatus(production.status) not in (ProductionStatus.APPROVED, ProductionStatus.QUEUED):
        from app.core.exceptions import InvalidGenerationParamsError
        raise InvalidGenerationParamsError(
            f"This production is '{production.status}', not approved — nothing to generate",
            details={"production_id": production.id, "status": production.status},
        )

    from app.services.entitlements import enforce_production_concurrency
    await enforce_production_concurrency(session, user_id, production.id)
    await ProductionBudgetService(session).reserve(production.id)

    production.status = ProductionStatus.RUNNING
    production.execution_status = ProductionStatus.RUNNING
    production.started_at = datetime.now(timezone.utc)
    await session.commit()

    enqueued = await start_production(session, production.id)
    metadata = dict(project.metadata_json or {})
    metadata["preview_started"] = True
    project.metadata_json = metadata
    await session.commit()
    return {**_project_dict(project), "production_id": production.id, "tasks_enqueued": enqueued}


@router.get("/{project_id}/characters")
async def list_characters(project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    await _get_owned_or_404(session, project_id, user_id)  # ownership check before listing
    characters = await MovieService(session).repo.list_characters(project_id)
    return {"characters": [_character_dict(c) for c in characters]}


@router.get("/{project_id}")
async def get_project(project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    repo_service = MovieService(session)
    project = await _get_owned_or_404(session, project_id, user_id)
    shots = await repo_service.repo.get_shots(project_id)
    characters = await repo_service.repo.list_characters(project_id)
    return {**_project_dict(project), "shots": [_shot_dict(s) for s in shots], "characters": [_character_dict(c) for c in characters]}


@router.get("")
async def list_projects(user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    projects = await MovieService(session).repo.list_for_user(user_id)
    return {"projects": [_project_dict(p) for p in projects]}


@router.post("/{project_id}/cancel")
async def cancel_project(project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """gap-closure: previously there was no way to cancel an in-flight
    project anywhere in the API — see MovieService.cancel_project."""
    project = await MovieService(session).cancel_project(user_id, project_id)
    return _project_dict(project)


@router.post("/{project_id}/render-editor")
async def render_editor_timeline(
    project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
):
    """Re-run only the final render from an already-generated production.

    No generation task is reset and no generation credits are reserved. The
    latest production must already have all non-render tasks completed/skipped.
    """
    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id).with_for_update()
    )
    project = result.scalar_one_or_none()
    if not project:
        raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
    if not project.current_production_id:
        raise HTTPException(status_code=409, detail="Generate the project before rendering editor changes")
    production = await session.get(Production, project.current_production_id)
    if not production or production.project_id != project.id or production.user_id != user_id:
        raise HTTPException(status_code=409, detail="No owned production is available to render")
    tasks = await dag.list_tasks_for_production(session, production.id)
    render_task = next((task for task in tasks if task.type == ProductionTaskType.RENDER), None)
    if not render_task:
        raise HTTPException(status_code=409, detail="This production has no render task")
    unfinished = [task for task in tasks if task.type != ProductionTaskType.RENDER and not ProductionTaskStatus(task.status).is_satisfied]
    if unfinished:
        raise HTTPException(status_code=409, detail="Wait for generation and production tasks to finish before rendering edits")
    if render_task.status == ProductionTaskStatus.RUNNING:
        raise HTTPException(status_code=409, detail="An editor render is already running")
    timeline = (project.metadata_json or {}).get("editor_timeline")
    if not isinstance(timeline, dict) or not isinstance(timeline.get("clips"), list):
        raise HTTPException(status_code=422, detail="Save an editor timeline before rendering")
    if not timeline["clips"]:
        raise HTTPException(status_code=422, detail="Add at least one clip to the timeline before rendering")

    render_task.status = ProductionTaskStatus.READY
    render_task.error = None
    render_task.output_json = None
    render_task.render_job_id = None
    render_task.started_at = None
    render_task.completed_at = None
    production.status = ProductionStatus.RUNNING
    production.execution_status = ProductionStatus.RUNNING
    production.error = None
    production.completed_at = None
    project.status = ProjectStatus.ASSEMBLING
    await session.commit()
    enqueued = await scheduler.start_production(session, production.id)
    if enqueued < 1:
        raise HTTPException(status_code=503, detail="The editor render could not be queued")
    return {"queued": True, "production_id": production.id, "message": "Editor render queued"}


@router.get("/{project_id}/render-job")
async def get_latest_render_job(project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """gap-closure: previously the only render observability was
    Project.status (a 3-value string). Returns the most recent RenderJob
    for this project — created by jobs/production.py::run_render_task —
    so the frontend can show real step/attempt/error detail, not just
    'assembling'."""
    from sqlalchemy import select
    from app.models.render_job import RenderJob

    await _get_owned_or_404(session, project_id, user_id)
    row = (
        await session.execute(
            select(RenderJob).where(RenderJob.project_id == project_id).order_by(RenderJob.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        return {"render_job": None}
    return {"render_job": {
        "id": row.id, "status": row.status, "progress_percent": row.progress_percent,
        "current_step": row.current_step, "attempt": row.attempt, "error": row.error,
        "started_at": row.started_at, "completed_at": row.completed_at,
    }}


@router.get("/{project_id}/production-tasks")
async def get_production_tasks(project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """gap-closure (0007): real per-scene/per-step task list, now backed
    by an actual dependency graph (orchestration/dag.py) rather than
    round 2's flat list. Kept for backward compatibility with existing
    frontend code that already polls this path; GET /productions/{id}/dag
    (routers/productions.py) returns the same tasks PLUS the dependency
    edges, for the frontend's DAG visualization."""
    project = await _get_owned_or_404(session, project_id, user_id)
    if not project.current_production_id:
        return {"tasks": []}
    from app.orchestration import dag
    tasks = await dag.list_tasks_for_production(session, project.current_production_id)
    return {"tasks": [
        {
            "id": t.id, "type": t.type, "scene_number": t.scene_number, "status": t.status,
            "shot_id": t.shot_id, "render_job_id": t.render_job_id, "error": t.error,
            "started_at": t.started_at, "completed_at": t.completed_at,
        }
        for t in tasks
    ]}
