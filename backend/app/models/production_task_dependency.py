"""gap-closure (0007): ProductionTaskDependency.

A real relational directed edge, not a JSON `depends_on` field on
ProductionTask â€” this is the distinction the DAG requires: the scheduler
(orchestration/scheduler.py) queries this table to find a task's
upstream dependencies and to find a completed task's downstream
dependents, rather than parsing/trusting a blob. See orchestration/dag.py
for how a ProductionPlan's scenes + fixed pipeline steps (voice/captions/
music/branding/render) get turned into task rows + these edges, with
cycle detection before anything is allowed to execute."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class ProductionTaskDependency(Base):
    __tablename__ = "production_task_dependency"
    __table_args__ = (UniqueConstraint("upstream_task_id", "downstream_task_id", name="uq_production_task_dependency_edge"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    production_id: Mapped[str] = mapped_column(String(128), ForeignKey("production.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    upstream_task_id: Mapped[str] = mapped_column(String(128), ForeignKey("production_task.id", ondelete="CASCADE"), index=True)
    downstream_task_id: Mapped[str] = mapped_column(String(128), ForeignKey("production_task.id", ondelete="CASCADE"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(128), default="requires")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

