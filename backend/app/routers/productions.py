"""gap-closure (0007): the Production API surface.

`/projects/{id}/plan`, `/approve-plan`, `/generate`, `/cancel` (routers/
projects.py) remain the primary entry points a project's UI actually
drives — they're unchanged in shape from rounds 1-2 so the existing
frontend flow keeps working, just backed by the new Production/DAG
domain underneath. This router adds the production-centric surface the
round-3 brief asked for explicitly: listing a project's production
history (a project can now have more than one), and inspecting a single
production's plan/budget/tasks/DAG/attempts directly by its own id,
which the project-scoped endpoints don't expose.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ProductionStatus, ProductionTaskStatus, ProductionTaskType, ProjectStatus
from app.core.exceptions import InvalidGenerationParamsError, PlanValidationError, ProductionNotFoundError
from app.dependencies import current_user_id, db_session
from app.models.production import Production
from app.models.production_task_dependency import ProductionTaskDependency
from app.models.production_task import ProductionTask
from app.models.project import Project, Shot
from app.models.generation import Generation
from app.orchestration import dag, executor
from app.orchestration.plan_validator import validate_plan
from app.orchestration.scheduler import cancel_production, start_production
from app.services.movie.service import MovieService
from app.services.production.budget_service import ProductionBudgetService

router = APIRouter(tags=["productions"])


async def _get_owned_production_or_404(session: AsyncSession, production_id: str, user_id: str) -> Production:
    production = await session.get(Production, production_id)
    if not production or production.user_id != user_id:
        raise ProductionNotFoundError("Production not found", details={"production_id": production_id})
    return production


def _production_dict(production: Production) -> dict:
    return {
        "id": production.id, "project_id": production.project_id, "status": production.status,
        "planning_status": production.planning_status, "execution_status": production.execution_status,
        "production_type": production.production_type, "plan_version": production.plan_version,
        "error": production.error, "started_at": production.started_at, "completed_at": production.completed_at,
        "cancelled_at": production.cancelled_at, "created_at": production.created_at,
    }


def _task_dict(task) -> dict:
    return {
        "id": task.id, "type": task.type, "scene_number": task.scene_number, "status": task.status,
        "shot_id": task.shot_id, "render_job_id": task.render_job_id, "error": task.error,
        "output_json": task.output_json, "started_at": task.started_at, "completed_at": task.completed_at,
    }


@router.get("/projects/{project_id}/productions")
async def list_productions_for_project(project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """gap-closure (0007): a project can have multiple production runs
    on record now — this is the actual history, not just
    `project.current_production_id`."""
    project = await MovieService(session).repo.get_owned(project_id, user_id)
    if not project:
        from app.core.exceptions import ProjectNotFoundError
        raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
    rows = (
        await session.execute(select(Production).where(Production.project_id == project_id).order_by(Production.created_at.desc()))
    ).scalars().all()
    return {"productions": [_production_dict(p) for p in rows]}


@router.get("/productions/{production_id}")
async def get_production(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    production = await _get_owned_production_or_404(session, production_id, user_id)
    return _production_dict(production)


@router.get("/productions/{production_id}/plan")
async def get_production_plan(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    await _get_owned_production_or_404(session, production_id, user_id)
    record = await executor.load_plan_record(session, production_id)
    if not record:
        return {"plan": None}
    return {"plan": {
        "id": record.id, "version": record.version, "status": record.status,
        "director_input": record.director_input, "plan_json": record.plan_json,
        "created_at": record.created_at, "approved_at": record.approved_at,
    }}


@router.post("/productions/{production_id}/validate")
async def validate_production_plan(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """Re-runs plan_validator against this production's currently-stored
    plan without approving anything — lets the frontend check "would
    this pass?" before calling approve."""
    production = await _get_owned_production_or_404(session, production_id, user_id)
    record = await executor.load_plan_record(session, production_id)
    if not record:
        return {"errors": ["No plan exists for this production yet."]}
    from app.orchestration.production_plan import ProductionPlan
    plan = ProductionPlan.model_validate(record.plan_json)
    errors = await validate_plan(session, user_id, production.project_id, plan)
    return {"errors": errors, "valid": len(errors) == 0}


@router.post("/productions/{production_id}/approve")
async def approve_production(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """Production-centric alias for POST /projects/{id}/approve-plan —
    only valid when `production_id` is still this project's
    `current_production_id` (approving an old, superseded production
    would be ambiguous, since the DAG-building step assumes it's
    operating on the project's live plan)."""
    production = await _get_owned_production_or_404(session, production_id, user_id)
    project = await session.get(Project, production.project_id)
    if project.current_production_id != production_id:
        raise InvalidGenerationParamsError(
            "This production has been superseded by a newer plan on this project and can no longer be approved.",
            details={"production_id": production_id, "current_production_id": project.current_production_id},
        )
    record = await executor.load_plan_record(session, production_id)
    from app.orchestration.production_plan import ProductionPlan
    plan = ProductionPlan.model_validate(record.plan_json)

    validation_errors = await validate_plan(session, user_id, production.project_id, plan)
    if validation_errors:
        raise PlanValidationError("This plan cannot be approved as-is", details={"errors": validation_errors})

    result = await executor.execute_plan(session, user_id, project, plan)
    return {"production_id": result.production_id, "shots_created": len(result.created_shots), "skipped_scenes": result.skipped_scenes, "warnings": result.warnings}


@router.post("/productions/{production_id}/start")
async def start_production_endpoint(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """Production-centric alias for POST /projects/{id}/generate."""
    production = await _get_owned_production_or_404(session, production_id, user_id)
    if ProductionStatus(production.status) not in (ProductionStatus.APPROVED, ProductionStatus.QUEUED):
        raise InvalidGenerationParamsError(
            f"This production is '{production.status}', not approved — nothing to start",
            details={"production_id": production_id, "status": production.status},
        )
    from datetime import datetime, timezone
    await ProductionBudgetService(session).reserve(production_id)
    production.status = ProductionStatus.RUNNING
    production.execution_status = ProductionStatus.RUNNING
    production.started_at = datetime.now(timezone.utc)
    await session.commit()
    enqueued = await start_production(session, production_id)
    return {"production_id": production_id, "tasks_enqueued": enqueued}


class ResumeProductionRequest(BaseModel):
    shot_id: str | None = Field(default=None, min_length=1, max_length=32)


@router.post("/productions/{production_id}/resume")
async def resume_production_endpoint(
    production_id: str,
    body: ResumeProductionRequest | None = None,
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(db_session),
):
    """Resume a failed multi-shot production without touching accepted clips.

    By default every failed SCENE task is retried. Optionally pass
    {"shot_id": "..."} to retry one failed shot, which is only allowed
    when it is the production's sole failed scene. Completed scene tasks
    and their charged generations are never reset or re-submitted.
    """
    production = await _get_owned_production_or_404(session, production_id, user_id)
    if production.status not in (ProductionStatus.FAILED, ProductionStatus.RUNNING):
        raise InvalidGenerationParamsError(
            "Only a failed or interrupted production can be resumed.",
            details={"production_id": production_id, "status": production.status},
        )
    tasks = await dag.list_tasks_for_production(session, production_id)
    failed_scene_tasks = [t for t in tasks if t.type == ProductionTaskType.SCENE and t.status == ProductionTaskStatus.FAILED]
    if not failed_scene_tasks:
        # Recover a failed render/voice task without regenerating successful clips.
        failed_non_scene = [t for t in tasks if t.type != ProductionTaskType.SCENE and t.status == ProductionTaskStatus.FAILED]
        if not failed_non_scene:
            raise InvalidGenerationParamsError("This production has no failed task to resume.", details={"production_id": production_id})

    requested_shot_id = body.shot_id if body else None
    if requested_shot_id:
        selected = [t for t in failed_scene_tasks if t.shot_id == requested_shot_id]
        if len(selected) != 1:
            raise InvalidGenerationParamsError("The requested shot is not a failed scene in this production.", details={"shot_id": requested_shot_id})
        target = selected[0]
        # A failed source invalidates only its dependency descendants, not
        # independent clips. Retry the target and any failed dependent shots;
        # reject if another independent failure also needs repair.
        ancestors = await dag.get_upstream_tasks(session, target.id)
        if any(a.type == ProductionTaskType.SCENE and a.status == ProductionTaskStatus.FAILED for a in ancestors):
            raise InvalidGenerationParamsError(
                "Retry the failed upstream shot first because this shot depends on its final frame.",
                details={"shot_id": requested_shot_id, "failed_upstream_task_ids": [a.id for a in ancestors if a.type == ProductionTaskType.SCENE and a.status == ProductionTaskStatus.FAILED]},
            )
        descendant_ids: set[str] = {target.id}
        queue = [target.id]
        while queue:
            current_id = queue.pop(0)
            for downstream in await dag.get_downstream_tasks(session, current_id):
                if downstream.id not in descendant_ids:
                    descendant_ids.add(downstream.id)
                    queue.append(downstream.id)
        retry_scene_tasks = [t for t in failed_scene_tasks if t.id in descendant_ids]
        unrelated = [t for t in failed_scene_tasks if t.id not in descendant_ids]
        if unrelated:
            raise InvalidGenerationParamsError(
                "Other independent shots have failed too. Resume all failed shots so the production can complete.",
                details={"failed_shot_ids": [t.shot_id for t in unrelated]},
            )
    else:
        retry_scene_tasks = failed_scene_tasks

    budget = await ProductionBudgetService(session).get_for_production(production_id)
    if budget:
        for task in retry_scene_tasks:
            if not task.shot_id:
                continue
            generation_count = await session.execute(
                select(func.count()).select_from(Generation).where(Generation.shot_id == task.shot_id)
            )
            count = int(generation_count.scalar_one())
            if count >= budget.max_retries_per_shot + 1:
                raise InvalidGenerationParamsError(
                    f"Shot retry limit reached for the {budget.budget_profile.replace('_', ' ')} budget profile.",
                    details={"shot_id": task.shot_id, "max_retries_per_shot": budget.max_retries_per_shot, "generation_count": count},
                )

    retry_estimate = 0
    if retry_scene_tasks:
        from app.services.generation.pricing import estimate_reservation
        from app.services.providers.fal.catalog import get_model
        for task in retry_scene_tasks:
            if not task.shot_id:
                continue
            shot = await session.get(Shot, task.shot_id)
            model = get_model(shot.model_id) if shot and shot.model_id else None
            if not shot or not model:
                raise InvalidGenerationParamsError(
                    "Could not estimate the retry budget for one of the failed shots; its model is no longer in the configured catalog.",
                    details={"shot_id": task.shot_id, "model_id": shot.model_id if shot else None},
                )
            _provider_cost, shot_credits = estimate_reservation(model, duration_seconds=shot.duration_seconds)
            retry_estimate += shot_credits
    # Preflight retry credits before changing any task/project state. The
    # budget update stays in this transaction so insufficient balance cannot
    # leave a failed production half-reset in RUNNING state.
    await ProductionBudgetService(session).resume_after_failure(
        production_id, additional_estimated_credits=retry_estimate,
    )

    # Keep successful scene outputs untouched. Reset only failed scene tasks
    # selected for retry; failed downstream work becomes BLOCKED and unlocks
    # only when persisted dependencies are satisfied.
    from app.orchestration.resume import prepare_resume_task_states
    prepare_resume_task_states(tasks, {task.id for task in retry_scene_tasks})

    from app.orchestration.scheduler import evaluate_and_unlock
    await session.flush()
    for task in tasks:
        if task.status == ProductionTaskStatus.BLOCKED:
            await evaluate_and_unlock(session, task.id)

    from datetime import datetime, timezone
    project = await session.get(Project, production.project_id)
    production.started_at = datetime.now(timezone.utc)
    production.status = ProductionStatus.RUNNING
    production.execution_status = ProductionStatus.RUNNING
    production.error = None
    production.completed_at = None
    if project:
        project.status = ProjectStatus.GENERATING
        project.error_message = None
        project.completed_at = None
    await session.commit()
    enqueued = await start_production(session, production_id)
    return {
        "production_id": production_id,
        "resumed": True,
        "retried_shot_ids": [t.shot_id for t in retry_scene_tasks if t.shot_id],
        "tasks_enqueued": enqueued,
        "preserved_completed_shots": [t.shot_id for t in tasks if t.type == ProductionTaskType.SCENE and t.status == ProductionTaskStatus.COMPLETED],
    }


@router.post("/productions/{production_id}/cancel")
async def cancel_production_endpoint(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """gap-closure (0007): cancels exactly this production (propagating
    through its DAG — orchestration/scheduler.py::cancel_production),
    as opposed to POST /projects/{id}/cancel, which cancels whichever
    production is currently `current_production_id`. The two coincide
    for a project with only one production on record."""
    production = await _get_owned_production_or_404(session, production_id, user_id)
    if ProductionStatus(production.status).is_terminal:
        raise InvalidGenerationParamsError(
            "This production has already finished and can no longer be cancelled",
            details={"production_id": production_id, "status": production.status},
        )
    from datetime import datetime, timezone
    await cancel_production(session, production_id)
    production.status = ProductionStatus.CANCELLED
    production.execution_status = ProductionStatus.CANCELLED
    production.cancelled_at = datetime.now(timezone.utc)
    await session.commit()
    await ProductionBudgetService(session).reconcile_on_failure(production_id)
    return _production_dict(production)


@router.get("/productions/{production_id}/budget")
async def get_production_budget(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    await _get_owned_production_or_404(session, production_id, user_id)
    budget = await ProductionBudgetService(session).get_for_production(production_id)
    if not budget:
        return {"budget": None}
    from app.models.production_budget import ProductionBudgetLedger
    ledger = (
        await session.execute(select(ProductionBudgetLedger).where(ProductionBudgetLedger.production_id == production_id).order_by(ProductionBudgetLedger.created_at.asc()))
    ).scalars().all()
    return {"budget": {
        "id": budget.id, "status": budget.status, "currency": budget.currency,
        "estimated_credits": budget.estimated_credits, "reserved_credits": budget.reserved_credits,
        "consumed_credits": budget.consumed_credits, "refunded_credits": budget.refunded_credits,
        "budget_profile": budget.budget_profile, "max_shots": budget.max_shots,
        "max_retries_per_shot": budget.max_retries_per_shot,
    }, "ledger": [
        {"id": e.id, "type": e.type, "amount": e.amount, "reference_type": e.reference_type, "reference_id": e.reference_id, "created_at": e.created_at}
        for e in ledger
    ]}


@router.get("/productions/{production_id}/tasks")
async def get_production_tasks_endpoint(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    await _get_owned_production_or_404(session, production_id, user_id)
    tasks = await dag.list_tasks_for_production(session, production_id)
    return {"tasks": [_task_dict(t) for t in tasks]}


@router.get("/productions/{production_id}/dag")
async def get_production_dag(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """gap-closure (0007): tasks PLUS the real dependency edges — what
    the frontend's DAG visualization (components/projects/
    production-dag-panel.tsx) actually renders, instead of a flat status
    list with no graph structure."""
    await _get_owned_production_or_404(session, production_id, user_id)
    tasks = await dag.list_tasks_for_production(session, production_id)
    edges = await dag.list_dependencies_for_production(session, production_id)
    return {
        "tasks": [_task_dict(t) for t in tasks],
        "edges": [{"upstream_task_id": e.upstream_task_id, "downstream_task_id": e.downstream_task_id} for e in edges],
    }


@router.get("/productions/{production_id}/attempts")
async def get_production_attempts(production_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """gap-closure (0007): GenerationAttempt — additive per-attempt audit
    history (see models/generation_attempt.py)."""
    await _get_owned_production_or_404(session, production_id, user_id)
    from app.models.generation_attempt import GenerationAttempt
    rows = (
        await session.execute(select(GenerationAttempt).where(GenerationAttempt.production_id == production_id).order_by(GenerationAttempt.started_at.asc()))
    ).scalars().all()
    return {"attempts": [
        {
            "id": a.id, "generation_id": a.generation_id, "production_task_id": a.production_task_id,
            "attempt_number": a.attempt_number, "provider": a.provider, "model_id": a.model_id,
            "status": a.status, "estimated_cost_usd": float(a.estimated_cost_usd) if a.estimated_cost_usd is not None else None,
            "actual_cost_usd": float(a.actual_cost_usd) if a.actual_cost_usd is not None else None,
            "actual_cost_source": a.actual_cost_source,
            "failure_type": a.failure_type, "error": a.error, "started_at": a.started_at, "completed_at": a.completed_at,
        }
        for a in rows
    ]}
