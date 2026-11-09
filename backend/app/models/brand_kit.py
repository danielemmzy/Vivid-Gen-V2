"""V2 Phase 11: account-level Brand Kit (spec Â§49). One user can have
several (e.g. one per client, for an agency use case) â€” not scoped to a
single project, so it can be reused across projects, matching how the
existing Character model works per-project but this is deliberately
account-wide."""
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BrandKit(Base, TimestampMixin):
    __tablename__ = "brand_kit"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)
    name: Mapped[str] = mapped_column(String(120))
    logo_s3_key: Mapped[str | None] = mapped_column(String(1024))
    watermark_s3_key: Mapped[str | None] = mapped_column(String(1024))
    # A real uploaded track, not AI-generated music â€” no music-generation
    # provider exists in this codebase (see V2_ARCHITECTURE_AUDIT.md), so
    # this is the honest, buildable version of spec Â§47's "music" concept:
    # the user supplies the track once per brand kit, it gets reused
    # across every video that brand kit is applied to.
    default_music_s3_key: Mapped[str | None] = mapped_column(String(1024))
    intro_asset_id: Mapped[str | None] = mapped_column(String(128))
    outro_asset_id: Mapped[str | None] = mapped_column(String(128))
    primary_color: Mapped[str | None] = mapped_column(String(16))  # hex, e.g. "#cda059"
    secondary_color: Mapped[str | None] = mapped_column(String(16))
    font_family: Mapped[str | None] = mapped_column(String(120))
    caption_style: Mapped[str] = mapped_column(String(128), default="minimal")
    cta_text: Mapped[str | None] = mapped_column(String(200))
    voice_id: Mapped[str | None] = mapped_column(String(120))
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)


def new_brand_kit_id() -> str:
    return "brand_" + uuid4().hex

