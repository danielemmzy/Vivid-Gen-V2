from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Generation(Base, TimestampMixin):
    """The single source of truth for every generation Vivid Gen has ever
    run — image, video, avatar/lip-sync, translation, or a movie shot.
    `user_id` is a logical reference to auth.user.id (Next.js/Prisma); there
    is deliberately no DB-level foreign key across schemas — see the
    architecture plan's Decision 2."""

    __tablename__ = "generation"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    title: Mapped[str | None] = mapped_column(String(200))  # user-editable label shown in the creations library

    # type: app.core.constants.GenerationType, status: GenerationStatus
    type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    model_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_model.id"))

    provider_request_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True)

    prompt: Mapped[str | None] = mapped_column(Text)
    input_s3_key: Mapped[str | None] = mapped_column(String(1024))
    secondary_input_s3_key: Mapped[str | None] = mapped_column(String(1024))  # e.g. audio for avatar/dub
    output_s3_key: Mapped[str | None] = mapped_column(String(1024))
    thumbnail_s3_key: Mapped[str | None] = mapped_column(String(1024))
    output_url: Mapped[str | None] = mapped_column(Text)

    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3))
    resolution: Mapped[str | None] = mapped_column(String(32))
    aspect_ratio: Mapped[str | None] = mapped_column(String(16))

    # Movie/storyboard linkage — null for standalone generations.
    project_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("project.id", ondelete="SET NULL"), index=True)
    shot_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("shot.id", ondelete="SET NULL"), index=True)
    character_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("character.id", ondelete="SET NULL"))

    estimated_provider_cost_usd: Mapped[float] = mapped_column(Numeric(18, 8), default=0)
    actual_provider_cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 8))
    credits_reserved: Mapped[int] = mapped_column(Integer, default=0)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0)

    moderation_verdict: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
