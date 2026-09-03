"""Movie/storyboard feature. A Project is a short film or multi-scene ad:
an ordered list of Shots, each optionally pinned to one or more Characters
for identity consistency across the whole piece — the single biggest
complaint in AI video communities (r/StableDiffusion, r/aivideo) is faces
and wardrobe drifting between clips. We address that the way the community
workaround does it manually: lock a character reference sheet once, reuse
its reference image on every shot that includes that character, and only
regenerate a shot (not the whole project) when someone edits one panel."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Character(Base, TimestampMixin):
    """A reusable identity reference: a locked set of images (front/side/back
    or a single hero shot) that every shot generation referencing this
    character is conditioned on. `reference_s3_keys` holds the character
    sheet; `locked_version` bumps whenever the sheet is regenerated so shots
    can record exactly which version they were generated against (useful
    for debugging drift — "this shot used v2, the sheet is now v3")."""

    __tablename__ = "character"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    reference_s3_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    locked_version: Mapped[int] = mapped_column(Integer, default=1)
    voice_id: Mapped[str | None] = mapped_column(String(120))  # for TTS/dubbing consistency


class Project(Base, TimestampMixin):
    """A movie/storyboard project: ordered shots assembled into one output
    video. Assembly (concat + transitions + audio mix) happens once every
    shot in the project reaches `completed` — see services/movie/service.py
    and jobs/media.py `AssembleMovieJob`."""

    __tablename__ = "project"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)  # ProjectStatus
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="16:9")
    resolution: Mapped[str] = mapped_column(String(32), default="1080p")
    output_s3_key: Mapped[str | None] = mapped_column(String(1024))
    output_duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Shot(Base, TimestampMixin):
    """One clip within a Project's storyboard. `order_index` fixes its place
    in the timeline; `character_ids` records which Character(s) this shot
    was conditioned on for continuity. `generation_id` points at the
    Generation row that actually produced the clip once submitted."""

    __tablename__ = "shot"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)  # ShotStatus

    prompt: Mapped[str] = mapped_column(Text)
    camera_notes: Mapped[str | None] = mapped_column(String(500))  # e.g. "slow dolly in, low angle"
    duration_seconds: Mapped[int] = mapped_column(Integer, default=5)
    character_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_id: Mapped[str | None] = mapped_column(String(64))

    generation_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("generation.id", ondelete="SET NULL"))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
