"""V2: explicit Project state machine (spec §54, §66).

V1 code sets `project.status` directly wherever convenient
(jobs/production.py's run_render_task, movie/service.py) without a shared
transition table — that still works and this file does not change those
call sites, since they only ever move forward along transitions this
table also allows (draft -> assembling -> ready/failed). What this adds
is a single place new V2 code (the plan/
approve-plan/generate endpoints) validates against, instead of each new
endpoint inventing its own "is this a legal transition?" check.
"""
from app.core.constants import ProjectStatus
from app.core.exceptions import VividGenError

_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.DRAFT: {ProjectStatus.PLANNING, ProjectStatus.GENERATING, ProjectStatus.CANCELLED},
    ProjectStatus.PLANNING: {ProjectStatus.AWAITING_APPROVAL, ProjectStatus.FAILED, ProjectStatus.CANCELLED},
    ProjectStatus.AWAITING_APPROVAL: {ProjectStatus.PLANNING, ProjectStatus.GENERATING, ProjectStatus.CANCELLED},
    ProjectStatus.GENERATING: {ProjectStatus.ASSEMBLING, ProjectStatus.FAILED, ProjectStatus.CANCELLED},
    ProjectStatus.ASSEMBLING: {ProjectStatus.READY, ProjectStatus.FAILED},
    ProjectStatus.READY: set(),  # terminal
    ProjectStatus.FAILED: {ProjectStatus.PLANNING, ProjectStatus.GENERATING},  # allow retry-from-failed
    ProjectStatus.CANCELLED: set(),  # terminal
}


class InvalidProjectTransitionError(VividGenError):
    http_status = 409
    code = "INVALID_PROJECT_TRANSITION"


def assert_transition(current: str, target: ProjectStatus) -> None:
    try:
        current_status = ProjectStatus(current)
    except ValueError:
        # A status value from before this table existed, or a plain string
        # that doesn't map to the enum. Don't hard-fail V1 rows over this —
        # only new V2 endpoints call this function at all.
        return
    allowed = _TRANSITIONS.get(current_status, set())
    if target not in allowed:
        raise InvalidProjectTransitionError(
            f"Cannot move project from '{current_status}' to '{target}'",
            details={"from": current_status.value, "to": target.value, "allowed": [s.value for s in allowed]},
        )
