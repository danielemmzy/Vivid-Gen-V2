"""Round 4: first-class CaptionTrack/CaptionSegment.

Before this, captions existed only as one .srt file (an Asset row) burned
into the render at RENDER-task time â€” real timing (round 2's P0.8 work)
but not a queryable domain object; you could not ask "what does the
caption say at 12.4s" without downloading and parsing the .srt. This
makes captions first-class: CaptionTrack (one per production, plus
styling) owning ordered CaptionSegment rows. The .srt file is now
DERIVED from these rows at render time (services/media/captions.py),
not the source of truth â€” CaptionTrack is.

Production-level/execution (an artifact of one production's render), not
project-level/shared â€” a re-render can produce a new CaptionTrack."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CaptionTrack(Base, TimestampMixin):
    __tablename__ = "caption_track"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    production_id: Mapped[str] = mapped_column(String(128), ForeignKey("production.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    language: Mapped[str] = mapped_column(String(16), default="en")
    style: Mapped[str] = mapped_column(String(128), default="minimal")
    font_family: Mapped[str | None] = mapped_column(String(64))
    primary_color: Mapped[str | None] = mapped_column(String(16))
    secondary_color: Mapped[str | None] = mapped_column(String(16))
    # The derived .srt, uploaded once the segments are finalized â€” kept
    # for the render path (burn_captions still consumes a file) and for
    # reuse by Content Factory variants/dubbed versions without re-deriving.
    source_asset_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("asset.id", ondelete="SET NULL"))


class CaptionSegment(Base):
    """No TimestampMixin â€” an immutable line within a CaptionTrack,
    ordered by `order_index` (not re-sorted by start_seconds at read
    time, so an intentionally out-of-order edit is preserved)."""
    __tablename__ = "caption_segment"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    caption_track_id: Mapped[str] = mapped_column(String(128), ForeignKey("caption_track.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(191))

    order_index: Mapped[int] = mapped_column(Integer)
    start_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    end_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    text: Mapped[str] = mapped_column(Text)
    speaker: Mapped[str | None] = mapped_column(String(64))

