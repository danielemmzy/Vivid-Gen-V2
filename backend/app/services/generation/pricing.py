"""Credit pricing math, isolated so it's unit-testable without touching the
DB or HTTP layer. This is where margin lives — see the architecture plan's
market research: per-second billing for generated video/images, per-minute
for translation/dubbing (matching HeyGen's model), matching how the
underlying provider itself bills us."""
import math
from decimal import Decimal

from app.core.config import settings
from app.core.constants import PricingUnit


def provider_cost_usd(model: dict, *, duration_seconds: float | None = None, num_images: int = 1) -> float:
    unit = model["unit"]
    price = model["price"]
    if unit == PricingUnit.SECOND:
        return price * float(duration_seconds or 1)
    if unit == PricingUnit.MINUTE:
        return price * (float(duration_seconds or 60) / 60.0)
    if unit == PricingUnit.IMAGE:
        return price * num_images
    return price  # flat


def calculate_credits(cost_usd: float) -> int:
    """USD provider cost -> retail credits, with markup and a floor so a
    near-zero-cost generation never becomes free to run."""
    if cost_usd <= 0:
        return settings.min_generation_credits
    retail_usd = Decimal(str(cost_usd)) * Decimal(str(settings.generation_markup_multiplier))
    credits = math.ceil(float(retail_usd) / settings.credit_usd_value)
    return max(settings.min_generation_credits, credits)


def estimate_reservation(
    model: dict, *, duration_seconds: float | None = None, num_images: int = 1, safety_margin: float = 1.0
) -> tuple[float, int]:
    """Returns (estimated_provider_cost_usd, credits_to_reserve). `safety_margin`
    lets callers over-reserve when the true output length isn't known until
    the provider processes it (e.g. avatar duration depends on the input
    audio) — see GenerationService.create_avatar, which reserves against a
    conservative worst case and refunds the delta once actual duration is
    known. Reserving less than the true cost is the failure mode that lets
    users get free generations; always round the reservation up, never down."""
    cost = provider_cost_usd(model, duration_seconds=duration_seconds, num_images=num_images) * safety_margin
    return cost, calculate_credits(cost)
