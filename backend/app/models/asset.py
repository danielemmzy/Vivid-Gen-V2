"""First-class project assets used by the V2 render pipeline."""
from typing import Any

from sqlalchemy import ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Asset(Base, TimestampMixin):
    __tablename__ = "asset"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)
    type: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(128))
    s3_key: Mapped[str] = mapped_column(String(1024))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3))
    scene_number: Mapped[int | None] = mapped_column(Integer)
    source_generation_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("generation.id", ondelete="SET NULL"))
    asset_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    license: Mapped[str | None] = mapped_column(String(64))
    attribution: Mapped[str | None] = mapped_column(Text)
    source_provider: Mapped[str | None] = mapped_column(String(128))
    source_external_id: Mapped[str | None] = mapped_column(String(191))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
