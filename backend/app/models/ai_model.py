from sqlalchemy import Boolean, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AIModel(Base, TimestampMixin):
    """A generation model exposed to users, backed by some provider. Pricing
    lives here (not hardcoded in services) so ops can retune margin without
    a deploy â€” see services/generation/pricing.py for how it's applied."""

    __tablename__ = "ai_model"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(128))
    provider_model_id: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    generation_type: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    commercial_use_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_movie_shots: Mapped[bool] = mapped_column(Boolean, default=False)
    max_resolution: Mapped[str] = mapped_column(String(16), default="1080p")

    # pricing_unit: one of app.core.constants.PricingUnit
    pricing_unit: Mapped[str] = mapped_column(String(128))
    provider_price_usd: Mapped[float] = mapped_column(Numeric(18, 8))
    price_per_unit: Mapped[float] = mapped_column(Numeric(18, 8), default=1)
    retail_multiplier: Mapped[float] = mapped_column(Numeric(8, 4), default=2.5)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    cost_strategy: Mapped[str] = mapped_column(String(40), default="catalog_unit_price", server_default="catalog_unit_price")
    cost_estimate_basis: Mapped[str | None] = mapped_column(String(255))

