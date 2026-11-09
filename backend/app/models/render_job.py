"""V2 gap-closure: RenderJob. Previously a Project's render step was only
ever a 3-value status string on `Project` itself â€” no step list, no
attempt count, no persisted manifest, no per-attempt error. This table is
the single source of render observability the frontend polls against.

One row per render attempt for a Project (a retried render creates a new
row with `attempt` incremented, not an overwrite â€” so a failed attempt's
error is never lost when a second attempt is kicked off)."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RenderJob(Base, TimestampMixin):
    __tablename__ = "render_job"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    production_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("production.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    # status: app.core.constants.RenderJobStatus
    status: Mapped[str] = mapped_column(String(128), default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(64))
    manifest_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text)
    output_asset_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("asset.id", ondelete="SET NULL"))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

