"""gap-closure (0007): the real DAG scheduler — event-driven, built on
the existing FastAPI + ARQ + Redis infrastructure (no new scheduler
process; a task's completion IS the trigger for evaluating what runs
next, dispatched as ordinary ARQ jobs).

This is the actual execution authority now. The distinction the round-3
brief drew is exactly this: having `ProductionTaskDependency` rows is a
data model; THIS module — where a task finishing atomically re-evaluates
its downstream neighbors and enqueues whichever just became READY — is
what makes it a scheduler. Nothing in this codebase iterates "for task in
tasks: enqueue(task)" and calls that execution; every enqueue after the
initial `start_production` call is a direct, traceable consequence of a
specific upstream task's completion.

Algorithm (matches the round-3 brief's spec almost verbatim):

    Production approved -> DAG built (orchestration/dag.py), all BLOCKED
    except roots, which are READY but NOT yet enqueued.
    generate/start_production -> enqueue every currently-READY task.
    task executes (a jobs/production.py ARQ job) -> on success/failure,
    calls on_task_completed here.
    on_task_completed:
        mark the task COMPLETED/FAILED
        if FAILED: propagate failure to every downstream task
                   (transitively) rather than leaving them BLOCKED
                   forever — see `_fail_downstream`
        if COMPLETED/SKIPPED: for each direct downstream task, check
                   whether ALL of ITS upstream tasks are now satisfied;
                   if so mark it READY and enqueue it
    repeat until every task is terminal -> Production reaches a terminal
    status (COMPLETED if the RENDER task succeeded, FAILED otherwise).
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ProductionStatus, ProductionTaskStatus, ProductionTaskType
from app.core.logging import get_logger
from app.models.production import Production
from app.models.production_task import ProductionTask
from app.models.project import Project
from app.orchestration import dag

logger = get_logger(__name__)

# task.type -> ARQ job function name (registered in jobs/queue.py /
# workers/worker.py). Kept as a plain dict rather than an if/elif chain
# so adding a new task type later is a one-line change here, not a new
# branch scattered through this file.
_JOB_FOR_TASK_TYPE = {
    ProductionTaskType.SCENE: "run_scene_task",
    ProductionTaskType.VOICE: "run_voice_task",
    ProductionTaskType.CAPTIONS: "run_captions_task",
    ProductionTaskType.MUSIC: "run_music_task",
    ProductionTaskType.BRANDING: "run_branding_task",
    ProductionTaskType.RENDER: "run_render_task",
}


async def evaluate_and_unlock(session: AsyncSession, task_id: str) -> bool:
    """If `task_id` is currently BLOCKED and every one of its upstream
    tasks is now satisfied (COMPLETED or SKIPPED — see
    ProductionTaskStatus.is_satisfied), flips it to READY. Returns
    whether it became READY. Does NOT enqueue — callers (dag.py at build
    time, `on_task_completed` below) decide separately whether enqueueing
    is appropriate yet (it isn't, at build time, before the production
    has actually started)."""
    task = await session.get(ProductionTask, task_id)
    if not task or task.status != ProductionTaskStatus.BLOCKED:
        return False
    upstream = await dag.get_upstream_tasks(session, task_id)
    if all(ProductionTaskStatus(u.status).is_satisfied for u in upstream):
        task.status = ProductionTaskStatus.READY
        return True
    return False


async def enqueue_task(session: AsyncSession, task: ProductionTask) -> None:
    """Marks the task RUNNING (optimistic — before the ARQ job actually
    starts) and dispatches it. Marking RUNNING here, not in the job
    itself, closes a real race: if the same task were enqueued twice
    (e.g. a retry of the enqueue call itself), the second ARQ job sees
    status != READY and no-ops instead of double-executing."""
    from app.jobs.queue import enqueue_production_task

    if task.status != ProductionTaskStatus.READY:
        logger.warning("enqueue_task_skipped_not_ready", task_id=task.id, status=task.status)
        return
    job_name = _JOB_FOR_TASK_TYPE.get(task.type)
    if not job_name:
        logger.error("enqueue_task_unknown_type", task_id=task.id, type=task.type)
        return
    task.status = ProductionTaskStatus.RUNNING
    task.started_at = datetime.now(timezone.utc)
    await session.commit()
    await enqueue_production_task(job_name, task.id)
    logger.info("task_enqueued", task_id=task.id, type=task.type, job=job_name)


async def start_production(session: AsyncSession, production_id: str) -> int:
    """Entry point called from POST /projects/{id}/generate (and
    POST /productions/{id}/start) — enqueues every task currently READY
    for this production. This is deliberately the ONLY place a task is
    enqueued without having been triggered by another task's completion
    — matching "Production approved -> DAG initialized -> find root
    tasks -> enqueue READY roots" exactly. Returns how many were
    enqueued."""
    tasks = await dag.list_tasks_for_production(session, production_id)
    ready = [t for t in tasks if t.status == ProductionTaskStatus.READY]
    for task in ready:
        await enqueue_task(session, task)
    logger.info("production_started", production_id=production_id, enqueued=len(ready))
    return len(ready)


async def on_task_completed(
    session: AsyncSession, task_id: str, *, success: bool, error: str | None = None,
) -> None:
    """The heart of the scheduler. Called by every jobs/production.py
    job function when a task finishes (success or failure) — this is
    what makes task completion the trigger for what runs next, not a
    flat pre-computed list. Caller is expected to have already set
    task.status to COMPLETED/FAILED/SKIPPED and any output_json BEFORE
    calling this (this function reads the already-set status to decide
    propagation, it doesn't set it) — see jobs/production.py for the
    pattern every job function follows."""
    task = await session.get(ProductionTask, task_id)
    if not task:
        logger.error("on_task_completed_missing_task", task_id=task_id)
        return

    if not ProductionTaskStatus(task.status).is_terminal:
        # Defensive: a caller forgot to set a terminal status before
        # calling this. Treat explicitly per `success` rather than
        # silently trusting an inconsistent state.
        task.status = ProductionTaskStatus.COMPLETED if success else ProductionTaskStatus.FAILED
        task.error = error
        task.completed_at = datetime.now(timezone.utc)
        await session.commit()

    if task.status == ProductionTaskStatus.FAILED:
        await _fail_downstream(session, task_id, reason=f"upstream task {task_id} failed")
        await _maybe_finalize_production(session, task.production_id, failed=True, error=task.error)
        return

    downstream = await dag.get_downstream_tasks(session, task_id)
    newly_ready: list[ProductionTask] = []
    for d in downstream:
        if await evaluate_and_unlock(session, d.id):
            newly_ready.append(d)
    await session.commit()

    for d in newly_ready:
        await enqueue_task(session, d)

    # A failed shot can have independent clips already in flight. Keep the
    # production resumable and defer budget release until those tasks finish;
    # otherwise a late successful clip could be charged after its estimate
    # had already been released. A user may still resume while status is RUNNING.
    if task.type != ProductionTaskType.RENDER and task.production_id:
        production_tasks = await dag.list_tasks_for_production(session, task.production_id)
        failed_tasks = [t for t in production_tasks if t.status == ProductionTaskStatus.FAILED]
        if failed_tasks:
            await _maybe_finalize_production(
                session, task.production_id, failed=True,
                error=failed_tasks[0].error or f"Task {failed_tasks[0].id} failed",
            )

    if task.type == ProductionTaskType.RENDER:
        # RENDER is the sink — its own job (jobs/production.py::
        # run_render_task) already marks Production COMPLETED on
        # success before calling this; this covers the case where
        # RENDER has no downstream (always true) and nothing else would
        # ever call _maybe_finalize_production for a clean success.
        await _maybe_finalize_production(session, task.production_id, failed=False)


async def _fail_downstream(session: AsyncSession, task_id: str, *, reason: str) -> None:
    """Transitively fails every downstream task of `task_id` that isn't
    already terminal — spec step 12: "If task permanently fails: fail
    dependent tasks." A BFS over the downstream edges, not just direct
    children, so a failure three levels up the graph still correctly
    fails everything that (transitively) needed it, rather than leaving
    a task BLOCKED forever because its direct parent was already
    terminal by the time propagation reached it."""
    queue = list(await dag.get_downstream_tasks(session, task_id))
    visited: set[str] = set()
    while queue:
        current = queue.pop(0)
        if current.id in visited or ProductionTaskStatus(current.status).is_terminal:
            continue
        visited.add(current.id)
        current.status = ProductionTaskStatus.FAILED
        current.error = reason
        current.completed_at = datetime.now(timezone.utc)
        queue.extend(await dag.get_downstream_tasks(session, current.id))
    await session.commit()
    if visited:
        logger.warning("failure_propagated", task_id=task_id, failed_downstream_count=len(visited))


async def _maybe_finalize_production(session: AsyncSession, production_id: str | None, *, failed: bool, error: str | None = None) -> None:
    if not production_id:
        return
    production = await session.get(Production, production_id)
    if not production or ProductionStatus(production.status).is_terminal:
        return
    production_tasks = await dag.list_tasks_for_production(session, production_id)
    nonterminal_tasks = [t for t in production_tasks if not ProductionTaskStatus(t.status).is_terminal]
    if nonterminal_tasks:
        logger.info(
            "production_finalization_deferred", production_id=production_id,
            pending_tasks=len(nonterminal_tasks), failure_pending=failed,
        )
        return
    # If any task failed, the production cannot complete successfully even if
    # the caller reached this helper from a successful independent clip.
    failed_tasks = [t for t in production_tasks if t.status == ProductionTaskStatus.FAILED]
    if failed_tasks:
        failed = True
        error = error or failed_tasks[0].error or f"Task {failed_tasks[0].id} failed"
    production.status = ProductionStatus.FAILED if failed else ProductionStatus.COMPLETED
    production.execution_status = production.status
    production.completed_at = datetime.now(timezone.utc)
    if failed:
        production.error = error
        project = await session.get(Project, production.project_id)
        if project:
            project.status = "failed"
            project.error_message = (error or "Production task failed")[:2000]
    await session.commit()

    # Budget reconciliation on failure: refund whatever was reserved but
    # never spent (tasks that got failed via propagation before they
    # ever submitted a generation never charged anything).
    if failed:
        from app.services.production.budget_service import ProductionBudgetService
        await ProductionBudgetService(session).reconcile_on_failure(production_id)

    logger.info("production_finalized", production_id=production_id, status=production.status)


async def cancel_production(session: AsyncSession, production_id: str) -> None:
    """gap-closure (0007): cancellation must propagate through the DAG —
    every non-terminal task is marked FAILED with a "cancelled" reason so
    no downstream task can ever become READY from a cancelled upstream
    (evaluate_and_unlock only ever unlocks from COMPLETED/SKIPPED
    upstream tasks, never FAILED, so this is sufficient to guarantee no
    new task starts after cancellation — no separate "is this production
    cancelled" check is needed in enqueue_task, though one is added
    there anyway as defense in depth against a task that was already
    RUNNING when cancellation was requested)."""
    tasks = await dag.list_tasks_for_production(session, production_id)
    for task in tasks:
        if not ProductionTaskStatus(task.status).is_terminal:
            task.status = ProductionTaskStatus.FAILED
            task.error = "Cancelled by user"
            task.completed_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info("production_cancelled", production_id=production_id, tasks_cancelled=len(tasks))
