"""Round 4, decision #2 (confirmed â€” NOT a reuse of Character): Product.

A product needs its own identity because it's conditioned into
generation differently than a Character â€” a product's reference photos
constrain shape/color/logo/material fidelity, not a person's face/body.
Keeping them as separate entities lets the Asset Router and Model Router
apply product-specific vs. character-specific conditioning logic without
a `kind` discriminator hack on one shared table.

Project-level/shared (confirmed ownership rule): a Product is reusable
across every Production run for its project, same tier as Character/
BrandKit â€” it does NOT get a production_id."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "product"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), ForeignKey("project.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(191), index=True)

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # features/variants: e.g. {"material": "brushed aluminum", "colors": ["black","silver"]}
    features: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    variants: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    visual_attributes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    logo_asset_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("asset.id", ondelete="SET NULL"))
    # The product's reference photo/video sheet â€” same role Character.
    # reference_s3_keys plays for people, kept as Asset ids (not raw S3
    # keys) here since product references are increasingly likely to be
    # user-uploaded Assets with their own provenance metadata already.
    reference_asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

