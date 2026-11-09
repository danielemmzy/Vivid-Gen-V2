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
    if model.get("cost_strategy") == "modal_runtime_estimate":
        # Modal charges for allocated GPU plus CPU/memory time, not only the
        # output-video seconds. This estimate uses a measured runtime ratio
        # and published resource rates; actual invoice costs are not available
        # per call in the callback and must be labelled as an estimate.
        runtime_seconds = float(duration_seconds or 1) * settings.modal_runtime_seconds_per_output_second
        resource_rate = (
            settings.modal_l40s_gpu_usd_per_second
            + settings.modal_cpu_usd_per_core_second * settings.modal_estimated_cpu_cores
            + settings.modal_memory_usd_per_gib_second * settings.modal_estimated_memory_gib
        )
        return runtime_seconds * resource_rate * settings.modal_cost_safety_factor
    if unit == PricingUnit.SECOND:
        return price * float(duration_seconds or 1)
    if unit == PricingUnit.MINUTE:
        return price * (float(duration_seconds or 60) / 60.0)
    if unit == PricingUnit.IMAGE:
        return price * num_images
    if unit == PricingUnit.MEGAPIXEL:
        return price * num_images
    return price  # flat


def calculate_credits(cost_usd: float, *, markup_multiplier: float | None = None) -> int:
    """USD provider cost -> retail credits, with markup and a floor so a
    near-zero-cost generation never becomes free to run."""
    if cost_usd <= 0:
        return settings.min_generation_credits
    multiplier = settings.generation_markup_multiplier if markup_multiplier is None else markup_multiplier
    retail_usd = Decimal(str(cost_usd)) * Decimal(str(multiplier))
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
    return cost, calculate_credits(cost, markup_multiplier=model.get("retail_multiplier"))


def modal_runtime_cost_usd(runtime_seconds: float) -> float:
    """Estimated Modal resource cost for measured function runtime seconds.

    This is not a provider invoice amount: Modal bills cold-start/container
    time and resource usage too, and per-call billing reports are not present
    in the worker callback. The source label must remain `modal_runtime_estimate`.
    """
    resource_rate = (
        settings.modal_l40s_gpu_usd_per_second
        + settings.modal_cpu_usd_per_core_second * settings.modal_estimated_cpu_cores
        + settings.modal_memory_usd_per_gib_second * settings.modal_estimated_memory_gib
    )
    return max(0.0, float(runtime_seconds)) * resource_rate
