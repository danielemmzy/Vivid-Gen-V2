"""gap-closure (0007): ProductionPlanRecord.

Named with the `Record` suffix specifically to avoid colliding with
`app.orchestration.production_plan.ProductionPlan` (the Pydantic schema
the Director actually returns) â€” code that needs both imports each under
its own name rather than aliasing on every import site.

Previously the canonical plan storage was `Project.metadata_json` (see
orchestration/executor.py's old `store_plan`/`load_plan`). This table is
now the canonical store; `Project.metadata_json` is read as a fallback
for any project created before this migration, but new code never writes
the plan there again. A plan is versioned per-Production (not
per-Project) since each Production owns exactly one approved plan, and a
re-plan on the same project starts a new Production."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProductionPlanRecord(Base, TimestampMixin):
    __tablename__ = "production_plan"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    production_id: Mapped[str] = mapped_column(String(128), ForeignKey("production.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    version: Mapped[int] = mapped_column(Integer, default=1)
    # status: app.core.constants.ProductionPlanStatus
    status: Mapped[str] = mapped_column(String(128), default="draft")

    director_input: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON)

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

