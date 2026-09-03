from fastapi import APIRouter

from app.core.cache import cache_get_or_set
from app.core.config import settings
from app.services.generation.pricing import calculate_credits, provider_cost_usd
from app.services.providers.fal.catalog import MODELS

router = APIRouter(prefix="/models", tags=["models"])


def _build_catalog() -> dict:
    result = []
    for m in MODELS.values():
        sample_cost = provider_cost_usd(m, duration_seconds=5 if m["unit"] == "second" else 60)
        result.append({**m, "credits_per_unit": calculate_credits(sample_cost) if m["unit"] != "image" else calculate_credits(m["price"])})
    return {"models": result}


@router.get("")
async def list_models():
    # The catalog is static config, not per-user data — safe to cache
    # globally. See core/cache.py for why this is a plain cache-aside call
    # rather than a decorator: it's obvious at the call site what's cached
    # and for how long.
    return await cache_get_or_set("vividgen:cache:model_catalog", settings.model_catalog_cache_ttl_seconds, _load_catalog)


async def _load_catalog() -> dict:
    return _build_catalog()
