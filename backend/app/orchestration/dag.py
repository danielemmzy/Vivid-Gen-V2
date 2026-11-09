"""gap-closure (0007): the real dependency DAG.

This replaces round 2's `orchestration/production_task.py` outright (that
module is deleted, not left alongside this one — see the round-3
acceptance requirement that the old flat execution path must stop being
the execution authority, not just gain a sibling). Everything that
touches ProductionTask/ProductionTaskDependency rows now goes through
this module or orchestration/scheduler.py.

What graph this codebase's media pipeline actually produces, honestly:

    SCENE_1  SCENE_2  ...  SCENE_N   MUSIC   BRANDING      <- roots, parallel
         \\      |      /
              VOICE                                         <- needs every
                |                                               scene's ACTUAL
            CAPTIONS                                            duration
                \\                    |          |
                 \\___________________|__________|
                              RENDER                         <- sink; needs
                                                                  everything

Independent scene roots can run in parallel, while continuity-dependent
shots carry real upstream edges. A scene that declares a reference scene
waits for that source scene's final clip, and multi-clip scenes serialize
subsequent clips behind their predecessor so the cached final frame exists.
VOICE still depends on every SCENE task, for a real reason: round 2 (P0.8) made
per-scene voiceover timing use each scene's ACTUAL rendered clip
duration, not its planned one — so VOICE cannot run until every scene's
actual duration is known. MUSIC and BRANDING resolve brand-kit
references only (no scene dependency) so they're independent roots that
can run alongside the scenes. RENDER is the one true join point.
"""
from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ProductionTaskStatus, ProductionTaskType
from app.core.exceptions import InvalidDagError
from app.core.logging import get_logger
from app.models.production_task import ProductionTask
from app.models.project import Shot
from app.models.production_task_dependency import ProductionTaskDependency

logger = get_logger(__name__)


@dataclass
class TaskSpec:
    """What the builder needs to create one ProductionTask row, before
    it exists in the DB (no id yet)."""
    type: str
    scene_number: int | None = None
    shot_id: str | None = None
    initial_status: str | None = None  # None -> computed from dependencies; set explicitly for already-terminal (COMPLETED/SKIPPED) tasks
    error: str | None = None


@dataclass
class DagSpec:
    """The graph, before it's written: tasks keyed by a caller-chosen key
    (e.g. "scene_3", "voice", "render") and edges by those same keys —
    lets the builder describe the graph declaratively and validate it
    BEFORE any row exists, rather than validating after the fact."""
    tasks: dict[str, TaskSpec] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (upstream_key, downstream_key)

    def add_task(self, key: str, spec: TaskSpec) -> None:
        if key in self.tasks:
            raise InvalidDagError(f"Duplicate task key '{key}' in DAG spec")
        self.tasks[key] = spec

    def add_edge(self, upstream_key: str, downstream_key: str) -> None:
        self.edges.append((upstream_key, downstream_key))


def validate_dag_spec(spec: DagSpec) -> list[str]:
    """Structural validation BEFORE any DB row is created: dangling edges
    (referencing a task key that doesn't exist), duplicate edges, and
    cycles (via DFS with a recursion stack). Returns every problem found,
    not just the first — mirrors plan_validator.py's style."""
    errors: list[str] = []

    seen_edges: set[tuple[str, str]] = set()
    for upstream_key, downstream_key in spec.edges:
        if upstream_key not in spec.tasks:
            errors.append(f"Dependency edge references unknown upstream task '{upstream_key}'")
        if downstream_key not in spec.tasks:
            errors.append(f"Dependency edge references unknown downstream task '{downstream_key}'")
        if (upstream_key, downstream_key) in seen_edges:
            errors.append(f"Duplicate dependency edge '{upstream_key}' -> '{downstream_key}'")
        seen_edges.add((upstream_key, downstream_key))

    if errors:
        return errors  # cycle detection assumes a structurally sound edge list

    adjacency: dict[str, list[str]] = {key: [] for key in spec.tasks}
    for upstream_key, downstream_key in spec.edges:
        adjacency[upstream_key].append(downstream_key)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {key: WHITE for key in spec.tasks}

    def _visit(node: str, path: list[str]) -> str | None:
        color[node] = GRAY
        path.append(node)
        for neighbor in adjacency[node]:
            if color[neighbor] == GRAY:
                cycle_start = path.index(neighbor)
                return " -> ".join(path[cycle_start:] + [neighbor])
            if color[neighbor] == WHITE:
                found = _visit(neighbor, path)
                if found:
                    return found
        path.pop()
        color[node] = BLACK
        return None

    for key in spec.tasks:
        if color[key] == WHITE:
            cycle = _visit(key, [])
            if cycle:
                errors.append(f"Dependency cycle detected: {cycle}")
                break  # one reported cycle is enough to reject the whole DAG

    return errors


async def materialize_dag(
    session: AsyncSession, spec: DagSpec, *, production_id: str, project_id: str, user_id: str,
) -> dict[str, ProductionTask]:
    """Validates `spec` (raises InvalidDagError with every problem found
    if invalid — a production is never allowed to start executing with a
    bad DAG) and writes real rows: one ProductionTask per spec task, one
    ProductionTaskDependency per edge. Computes each task's initial
    status: an explicit `initial_status` (already-terminal tasks, e.g. a
    skipped/pass-through scene) is kept as-is; everything else starts
    BLOCKED if it has any upstream edge, READY if it has none — then a
    readiness propagation pass (`evaluate_and_unlock`, imported lazily to
    avoid a circular import with scheduler.py) runs once immediately so
    a task whose only dependencies were already-terminal at build time
    (e.g. VOICE when every scene turned out to be a skip/pass-through)
    is correctly READY rather than stuck BLOCKED until nothing ever
    triggers it."""
    errors = validate_dag_spec(spec)
    if errors:
        raise InvalidDagError("Production plan produced an invalid task graph", details={"errors": errors})

    has_upstream = {key: False for key in spec.tasks}
    for _upstream_key, downstream_key in spec.edges:
        has_upstream[downstream_key] = True

    rows: dict[str, ProductionTask] = {}
    for key, task_spec in spec.tasks.items():
        if task_spec.initial_status is not None:
            status = task_spec.initial_status
        else:
            status = ProductionTaskStatus.BLOCKED if has_upstream[key] else ProductionTaskStatus.READY
        row = ProductionTask(
            id="ptask_" + uuid4().hex, production_id=production_id, project_id=project_id, user_id=user_id,
            type=task_spec.type, scene_number=task_spec.scene_number, shot_id=task_spec.shot_id,
            status=status, error=task_spec.error,
        )
        session.add(row)
        rows[key] = row
    await session.flush()

    for upstream_key, downstream_key in spec.edges:
        session.add(ProductionTaskDependency(
            id="ptdep_" + uuid4().hex, production_id=production_id, user_id=user_id,
            upstream_task_id=rows[upstream_key].id, downstream_task_id=rows[downstream_key].id,
        ))
    await session.flush()

    # A task whose dependencies were already all satisfied at build time
    # (e.g. every SCENE task ended up SKIPPED/COMPLETED immediately) must
    # become READY now, not stay BLOCKED forever waiting for a completion
    # event that already happened before this task existed.
    from app.orchestration.scheduler import evaluate_and_unlock  # local import: scheduler imports dag for enqueue helpers

    for row in rows.values():
        if row.status == ProductionTaskStatus.BLOCKED:
            await evaluate_and_unlock(session, row.id)

    logger.info("dag_materialized", production_id=production_id, tasks=len(rows), edges=len(spec.edges))
    return rows


async def get_task(session: AsyncSession, task_id: str) -> ProductionTask | None:
    return await session.get(ProductionTask, task_id)


async def get_upstream_tasks(session: AsyncSession, task_id: str) -> list[ProductionTask]:
    rows = (
        await session.execute(
            select(ProductionTask)
            .join(ProductionTaskDependency, ProductionTaskDependency.upstream_task_id == ProductionTask.id)
            .where(ProductionTaskDependency.downstream_task_id == task_id)
        )
    ).scalars().all()
    return list(rows)


async def get_downstream_tasks(session: AsyncSession, task_id: str) -> list[ProductionTask]:
    rows = (
        await session.execute(
            select(ProductionTask)
            .join(ProductionTaskDependency, ProductionTaskDependency.downstream_task_id == ProductionTask.id)
            .where(ProductionTaskDependency.upstream_task_id == task_id)
        )
    ).scalars().all()
    return list(rows)


async def list_tasks_for_production(session: AsyncSession, production_id: str) -> list[ProductionTask]:
    rows = (
        await session.execute(
            select(ProductionTask).where(ProductionTask.production_id == production_id)
            .outerjoin(Shot, ProductionTask.shot_id == Shot.id)
            .order_by(ProductionTask.scene_number.asc().nulls_last(), Shot.order_index.asc().nulls_last(), ProductionTask.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


async def list_dependencies_for_production(session: AsyncSession, production_id: str) -> list[ProductionTaskDependency]:
    rows = (
        await session.execute(select(ProductionTaskDependency).where(ProductionTaskDependency.production_id == production_id))
    ).scalars().all()
    return list(rows)


async def get_task_for_shot(session: AsyncSession, shot_id: str) -> ProductionTask | None:
    return (await session.execute(select(ProductionTask).where(ProductionTask.shot_id == shot_id))).scalar_one_or_none()


async def get_task_by_type(session: AsyncSession, production_id: str, task_type: str) -> ProductionTask | None:
    """For the four whole-production task types (VOICE/CAPTIONS/MUSIC/
    BRANDING/RENDER) there's exactly one row per production; SCENE has
    one per scene_number, so callers needing a specific scene use
    `get_task_for_shot` instead."""
    return (
        await session.execute(
            select(ProductionTask).where(ProductionTask.production_id == production_id, ProductionTask.type == task_type)
        )
    ).scalar_one_or_none()
