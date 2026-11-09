"""V2 gap-closure, revised (0006): Content Factory is now two stages, not
one, matching the canonical spec's `Master -> ContentVariant -> Export`:

- `ContentVariant`: a reframed derivative of a Project's Master for a
  given platform/aspect-ratio (services/export/service.py's
  `reframe_video`, reusing the same center-crop logic Shorts already
  uses). Building this is the actual rendering work.
- `Export`: a packaged, downloadable deliverable pointing at a variant
  (or, for platform="master", at the original Master with no reframe).
  Splitting these out means a single variant could in principle back more
  than one Export (e.g. different codecs) without re-rendering the
  reframe â€” this pass only ever creates one Export per variant, but the
  schema no longer conflates "the rendering" with "the deliverable
  record" the way the previous single-`Export`-row version did.

Honest scope note, unchanged from the original Export docstring: neither
of these generates per-platform titles/descriptions/thumbnails â€” that
needs product/prompt-design work beyond a mechanical render step."""
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ContentVariant(Base, TimestampMixin):
    __tablename__ = "content_variant"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    production_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("production.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    platform: Mapped[str] = mapped_column(String(128))  # "youtube" | "tiktok" | "instagram_reels" | "master" | ...
    aspect_ratio: Mapped[str] = mapped_column(String(16))
    # status: app.core.constants.ExportStatus (reused â€” same processing/completed/failed lifecycle)
    status: Mapped[str] = mapped_column(String(128), default="processing")
    asset_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("asset.id", ondelete="SET NULL"))
    s3_key: Mapped[str | None] = mapped_column(String(1024))
    error: Mapped[str | None] = mapped_column(Text)


class Export(Base, TimestampMixin):
    __tablename__ = "export"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    production_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("production.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)
    # gap-closure (0006): an Export now points at the ContentVariant it
    # packages, rather than duplicating platform/aspect_ratio itself.
    # Nullable for backward compatibility with rows created by the
    # previous pass, which had no variant to point at.
    variant_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("content_variant.id", ondelete="CASCADE"))

    platform: Mapped[str] = mapped_column(String(128))
    aspect_ratio: Mapped[str] = mapped_column(String(16))
    codec: Mapped[str] = mapped_column(String(16), default="h264")
    # status: app.core.constants.ExportStatus
    status: Mapped[str] = mapped_column(String(128), default="processing")
    asset_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("asset.id", ondelete="SET NULL"))
    s3_key: Mapped[str | None] = mapped_column(String(1024))
    error: Mapped[str | None] = mapped_column(Text)

