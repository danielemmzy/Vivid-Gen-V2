"""The Model Router.

Selects which catalog model should execute a given scene. Round 4
(confirmed decision) extends this from capability + quality-tier + price
to a real deterministic score combining quality, price, provider health
(orchestration/provider_health.py), latency, and — when a production's
remaining budget is known — cost-budget exclusion. This is deliberately
NOT an LLM decision at execution time: the score is a fixed, documented
formula over measured data (ProviderHealth + catalog metadata), the same
kind of application logic a rules engine would run, not a prompt.

Two-pass selection: pass 1 excludes NOT_CONFIGURED and, when at least one
other candidate exists, FAILED providers and anything over budget. If
pass 1 leaves nothing (every candidate is degraded or over budget), pass
2 retries without the hard exclusions — a struggling provider is still a
better outcome than no generation at all, exactly the "still usable as a
last resort" behavior confirmed for degraded (not NOT_CONFIGURED) states.
"""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import ProviderAvailabilityStatus
from app.core.exceptions import VividGenError
from app.orchestration import provider_health
from app.orchestration.production_plan import QualityMode
from app.services.generation.pricing import estimate_reservation
from app.services.providers.fal.catalog import MODELS
from app.services.providers.registry import provider_is_configured

_QUALITY_ORDER = {
    "low": ["economy", "standard", "premium"],
    "medium": ["standard", "economy", "premium"],
    "high": ["premium", "standard", "economy"],
    # Backward-compatible aliases for existing stored production plans.
    "fast": ["economy", "standard", "premium"],
    "balanced": ["standard", "premium", "economy"],
    "best": ["premium", "standard", "economy"],
}
_QUALITY_ALIASES = {"fast": "low", "balanced": "medium", "best": "high"}
_QUALITY_SCORE = {"premium": 1.0, "standard": 0.6, "economy": 0.3}
_HEALTH_SCORE = {
    ProviderAvailabilityStatus.AVAILABLE: 1.0,
    ProviderAvailabilityStatus.RATE_LIMITED: 0.45,
    ProviderAvailabilityStatus.TEMPORARILY_UNAVAILABLE: 0.35,
    ProviderAvailabilityStatus.FAILED: 0.05,
    ProviderAvailabilityStatus.NOT_CONFIGURED: 0.0,
}


class NoRoutableModelError(VividGenError):
    http_status = 422
    code = "NO_ROUTABLE_MODEL"


@dataclass
class RoutingRequest:
    capability: str  # a GenerationType value: "text_to_video", "image_to_video", "text_to_image", ...
    quality_mode: QualityMode = "medium"
    exclude_model_ids: tuple[str, ...] = ()  # already-tried models, for fallback routing
    require_movie_shot_support: bool = False  # True when routing for a Project Shot — see executor.py
    duration_seconds: float | None = None  # for cost estimation, when known
    remaining_budget_credits: int | None = None  # a production's remaining budget, when known — see services/production/budget_service.py


def candidates_for(capability: str, *, require_movie_shot_support: bool = False) -> list[dict]:
    pool = [m for m in MODELS.values() if m.get("enabled", True) and m["type"] == capability]
    if require_movie_shot_support:
        pool = [m for m in pool if m.get("supports_movie_shots")]
    return pool


async def _score(session: AsyncSession, model: dict, request: RoutingRequest, *, allow_degraded: bool) -> float | None:
    """Returns None if this candidate is hard-excluded (unless
    `allow_degraded`, the last-resort pass). NOT_CONFIGURED is ALWAYS a
    hard exclusion, even in the last-resort pass — a missing credential
    can never be worked around by trying harder, unlike a degraded-but-
    configured provider."""
    # Never route to a provider whose required credentials are missing. This
    # avoids reserving credits for a job that can only fail at submission.
    # The explicit fake override remains available for local tests.
    effective_provider = "fake" if settings.generation_provider == "fake" else model["provider"]
    if not provider_is_configured(effective_provider):
        return None

    status = await provider_health.get_status(session, provider=model["provider"], model_id=model["id"], capability=request.capability)
    if status == ProviderAvailabilityStatus.NOT_CONFIGURED:
        return None
    if status == ProviderAvailabilityStatus.FAILED and not allow_degraded:
        return None

    if request.remaining_budget_credits is not None and request.duration_seconds is not None:
        _cost_usd, credits = estimate_reservation(model, duration_seconds=request.duration_seconds)
        if credits > request.remaining_budget_credits * settings.router_max_price_fraction_of_remaining_budget and not allow_degraded:
            return None

    normalized_mode = _QUALITY_ALIASES.get(request.quality_mode, request.quality_mode)
    tier_order = _QUALITY_ORDER[normalized_mode]
    quality_rank = tier_order.index(model.get("quality_tier", "standard"))
    quality_score = 1.0 - (quality_rank / max(len(tier_order) - 1, 1))

    all_prices = [m["price"] for m in candidates_for(request.capability)]
    price_range = (max(all_prices) - min(all_prices)) if all_prices else 0
    price_score = 1.0 - ((model["price"] - min(all_prices)) / price_range) if price_range else 1.0

    health_score = _HEALTH_SCORE.get(status, 0.5)

    health_row = await provider_health.get_health(session, provider=model["provider"], model_id=model["id"], capability=request.capability)
    if health_row and health_row.avg_latency_ms is not None:
        latency_score = max(0.0, 1.0 - float(health_row.avg_latency_ms) / 60000.0)  # 60s+ average latency scores ~0
    else:
        latency_score = 0.7  # neutral — no data yet, don't punish an untested model

    return (
        settings.router_weight_quality * quality_score
        + settings.router_weight_price * price_score
        + settings.router_weight_health * health_score
        + settings.router_weight_latency * latency_score
    )


async def select_model(session: AsyncSession, request: RoutingRequest) -> dict:
    """Select a model for a user quality level.

    Quality is a product decision, not merely a scoring hint:
    low prefers economy, medium prefers standard then economy/premium, and
    high prefers premium. Price/health/latency decide between models in the
    same tier and can force a fallback when the preferred tier is unavailable
    or exceeds the caller's remaining budget.
    """
    pool = [
        m for m in candidates_for(request.capability, require_movie_shot_support=request.require_movie_shot_support)
        if m["id"] not in request.exclude_model_ids
    ]
    if not pool:
        raise NoRoutableModelError(
            f"No model supports capability '{request.capability}'"
            + (" for a project shot" if request.require_movie_shot_support else ""),
            details={"capability": request.capability, "excluded": list(request.exclude_model_ids)},
        )

    normalized_mode = _QUALITY_ALIASES.get(request.quality_mode, request.quality_mode)
    tier_order = _QUALITY_ORDER[normalized_mode]
    for tier in tier_order:
        tier_pool = [m for m in pool if m.get("quality_tier", "standard") == tier]
        if not tier_pool:
            continue

        scored = [(m, await _score(session, m, request, allow_degraded=False)) for m in tier_pool]
        usable = [(m, s) for m, s in scored if s is not None]
        if usable:
            usable.sort(key=lambda t: -t[1])
            return usable[0][0]

        # If every model in this preferred tier is degraded, still allow a
        # configured model in that tier before dropping to another quality.
        degraded = [(m, await _score(session, m, request, allow_degraded=True)) for m in tier_pool]
        usable_degraded = [(m, s) for m, s in degraded if s is not None]
        if usable_degraded:
            usable_degraded.sort(key=lambda t: -t[1])
            return usable_degraded[0][0]

    raise NoRoutableModelError(
        f"Every model for capability '{request.capability}' is unavailable for quality '{normalized_mode}'",
        details={"capability": request.capability, "quality_mode": normalized_mode},
    )


async def select_with_fallback(session: AsyncSession, request: RoutingRequest, max_attempts: int = 3) -> list[dict]:
    """Returns an ordered fallback chain (primary first) instead of a
    single model, for callers that want to retry against a different
    model on a transient provider failure without re-deriving the
    request. Never includes two models of different capability — every
    candidate is filtered by `capability` first."""
    chain: list[dict] = []
    excluded: tuple[str, ...] = request.exclude_model_ids
    for _ in range(max_attempts):
        try:
            model = await select_model(session, RoutingRequest(
                request.capability, request.quality_mode, excluded, request.require_movie_shot_support,
                request.duration_seconds, request.remaining_budget_credits,
            ))
        except NoRoutableModelError:
            break
        chain.append(model)
        excluded = (*excluded, model["id"])
    return chain
