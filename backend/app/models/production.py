"""gap-closure (0007): Production.

Previously a "production run" was implicit â€” Project.status doubled as
both the project's lifecycle AND its (single, only-ever-one) execution
run, and the plan lived in Project.metadata_json. That meant a project
could never have more than one production run on record, and there was
no single object to point a budget, a DAG, or a render at.

A Project now owns zero or more Productions. `project.current_production_id`
is a convenience pointer to the most recent one (used by most read paths
that only care about "what's this project doing right now"), but is not
the source of truth â€” querying `production` by `project_id` always is.

`status` is the overall production lifecycle; `planning_status` and
`execution_status` are split out because a production can be actively
planning (Director call in flight) independent of whether execution has
started â€” this mirrors the existing plan/approve/generate three-step
safety flow (routers/projects.py) rather than replacing it."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Production(Base, TimestampMixin):
    __tablename__ = "production"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    # status/planning_status/execution_status: app.core.constants.ProductionStatus
    status: Mapped[str] = mapped_column(String(128), default="draft")
    planning_status: Mapped[str] = mapped_column(String(128), default="draft")
    execution_status: Mapped[str] = mapped_column(String(128), default="draft")

    production_type: Mapped[str] = mapped_column(String(128), default="video")
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

