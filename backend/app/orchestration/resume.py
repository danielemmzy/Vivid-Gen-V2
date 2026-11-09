"""Pure task-state transitions used when resuming a failed production."""
from app.core.constants import ProductionTaskStatus, ProductionTaskType


def prepare_resume_task_states(tasks: list, retry_scene_task_ids: set[str]) -> None:
    """Reset selected failed clips and failed downstream work only.

    Accepted/completed scene tasks are intentionally immutable here: their
    generation IDs, stored clips and credit ledger movements remain intact.
    Failed non-scene tasks are reset to BLOCKED and will be unlocked by the
    scheduler after all their upstream dependencies are satisfied.
    """
    for task in tasks:
        if task.type == ProductionTaskType.SCENE and task.id in retry_scene_task_ids and task.status == ProductionTaskStatus.FAILED:
            task.status = ProductionTaskStatus.BLOCKED
            task.error = None
            task.started_at = None
            task.completed_at = None
            task.output_json = None
        elif task.type != ProductionTaskType.SCENE and task.status == ProductionTaskStatus.FAILED:
            task.status = ProductionTaskStatus.BLOCKED
            task.error = None
            task.started_at = None
            task.completed_at = None
            task.output_json = None
