"""Movie/storyboard feature. A Project is a short film or multi-scene ad:
an ordered list of Shots, each optionally pinned to one or more Characters
for identity consistency across the whole piece â€” the single biggest
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
    for debugging drift â€” "this shot used v2, the sheet is now v3")."""

    __tablename__ = "character"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    reference_s3_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    locked_version: Mapped[int] = mapped_column(Integer, default=1)
    voice_id: Mapped[str | None] = mapped_column(String(120))  # for TTS/dubbing consistency


class Project(Base, TimestampMixin):
    """A movie/storyboard project: ordered shots assembled into one output
    video. Assembly (concat + transitions + audio mix) happens once every
    shot in the project reaches `completed` â€” see services/movie/service.py
    and jobs/production.py's `run_render_task` (the DAG's RENDER task)."""

    __tablename__ = "project"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(128), default="draft", index=True)  # ProjectStatus
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="16:9")
    resolution: Mapped[str] = mapped_column(String(128), default="1080p")
    output_s3_key: Mapped[str | None] = mapped_column(String(1024))
    output_duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # gap-closure (0007): convenience pointer to this project's most
    # recent Production run â€” NOT the source of truth (a project can
    # have multiple Productions; see models/production.py). Anything
    # needing full history queries `production` by project_id directly.
    current_production_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("production.id", ondelete="SET NULL"))


class Shot(Base, TimestampMixin):
    """One clip within a Project's storyboard. `order_index` fixes its place
    in the timeline; `character_ids` records which Character(s) this shot
    was conditioned on for continuity. `generation_id` points at the
    Generation row that's currently the ACTIVE version of this shot;
    `generation_history` (added in migration 0004, V2) holds every
    previously-active generation_id, oldest first, so a regenerated shot
    never loses its earlier attempts â€” see MovieService.regenerate_shot
    and select_shot_version."""

    __tablename__ = "shot"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    # gap-closure (0007): a Shot is execution-owned by whichever
    # Production created it (ownership rule: Shot is execution-level,
    # not shared like Asset/Character/BrandKit). Nullable for shots that
    # predate this migration; every shot created by orchestration/dag.py
    # sets this.
    production_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("production.id", ondelete="SET NULL"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(128), default="pending", index=True)  # ShotStatus
    # gap-closure (0006): links a shot back to the ScenePlan.scene_number
    # it was created from â€” null for shots added manually (not via a
    # Director plan). Needed for real per-scene audio timing: without
    # this, a voiceover line couldn't be placed at its actual scene's
    # position, only concatenated undifferentiated with every other line.
    # See orchestration/render_manifest_builder.py.
    scene_number: Mapped[int | None] = mapped_column(Integer)
    # Round 4, decision #5: real scene-to-scene continuity. Set ONLY when
    # the ProductionPlan explicitly declares this scene's
    # `reference_scene_number` pointing at an earlier scene â€” never
    # invented by the executor to "demonstrate" a DAG edge. When set,
    # this shot's generation is conditioned on the referenced shot's
    # ACTUAL completed output (resolved through the Asset Router), and
    # the DAG has a real edge: the referenced shot's SCENE task must
    # complete before this one can become READY. See orchestration/dag.py.
    reference_shot_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("shot.id", ondelete="SET NULL"))
    # Persist the extracted end frame so retries/resumes reuse the same asset.
    reference_frame_s3_key: Mapped[str | None] = mapped_column(String(1024))
    reference_frame_generation_id: Mapped[str | None] = mapped_column(String(128))
    continuity_mode: Mapped[str] = mapped_column(String(128), default="none")
    reference_image_s3_key: Mapped[str | None] = mapped_column(String(1024))

    prompt: Mapped[str] = mapped_column(Text)
    camera_notes: Mapped[str | None] = mapped_column(String(500))  # e.g. "slow dolly in, low angle"
    duration_seconds: Mapped[int] = mapped_column(Integer, default=5)  # provider-supported inference duration
    timeline_duration_seconds: Mapped[float | None] = mapped_column(Numeric(8, 3))  # usable duration after timeline trim
    character_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    product_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("product.id", ondelete="SET NULL"))
    model_id: Mapped[str | None] = mapped_column(String(64))

    generation_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("generation.id", ondelete="SET NULL"))
    generation_history: Mapped[list[str]] = mapped_column(JSON, default=list)  # V2: past generation_ids, oldest first
    # NOTE: retry tracking lives on Generation.retry_count (migration 0005) â€”
    # a shot's retries are its active generation's retries. The old
    # Shot.retry_count column was write-only dead weight and was dropped.

