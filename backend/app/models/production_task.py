"""gap-closure (0007): ProductionTask is now a real DAG node.

Round 2 (0006) introduced this table as a deliberately flat, always-
parallel per-scene/per-step list â€” its own docstring said so explicitly.
This round replaces that: a task now has real upstream/downstream edges
(ProductionTaskDependency), a BLOCKED/READY/RUNNING status lifecycle
driven by orchestration/scheduler.py (not just PENDING/RUNNING), and an
`output_json` field holding whatever artifact references it produced
(e.g. the VOICE task's synthesized segment asset refs, which the RENDER
task then reads directly rather than re-deriving them) â€” see
orchestration/dag.py for how a plan gets turned into a graph of these.

`scene_number`/`shot_id`/`render_job_id` are unchanged from round 2 and
still mean what they meant there."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProductionTask(Base, TimestampMixin):
    __tablename__ = "production_task"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    production_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("production.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    # type: app.core.constants.ProductionTaskType
    type: Mapped[str] = mapped_column(String(128))
    scene_number: Mapped[int | None] = mapped_column(Integer)
    # status: app.core.constants.ProductionTaskStatus (BLOCKED/READY/RUNNING/COMPLETED/FAILED/SKIPPED)
    status: Mapped[str] = mapped_column(String(128), default="blocked")
    shot_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("shot.id", ondelete="SET NULL"))
    render_job_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("render_job.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(Text)
    # gap-closure (0007): each task's produced artifact references â€” see
    # module docstring. Shape depends on `type`; orchestration/dag.py's
    # per-type job functions are the only code that needs to know it.
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

