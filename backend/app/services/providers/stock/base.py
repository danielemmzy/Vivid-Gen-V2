"""Round 4, decision #1 (confirmed): real stock-media search, not a
disguised URL passthrough.

Round 3 added `orchestration/asset_fetch.py` — fetch a SPECIFIC,
already-known URL. That stays exactly as it was, as its own source type
(`AssetSourceType.STOCK_URL`) for "I already have a licensed clip, here's
the URL." This module is the other, previously-missing half: actually
searching a stock library by keyword/orientation/duration
(`AssetSourceType.STOCK_SEARCH`) and returning ranked candidates with
real license/attribution metadata — orchestration/asset_router.py picks
one and downloads it exactly like a URL-sourced asset.
"""
from dataclasses import dataclass
from typing import Protocol

from app.core.constants import ProviderAvailabilityStatus


@dataclass
class StockCandidate:
    external_id: str
    url: str               # the actual downloadable file URL (not the provider's page URL)
    preview_url: str | None
    width: int | None
    height: int | None
    duration_seconds: float | None  # None for images
    license: str
    attribution: str
    content_type: str      # "image/jpeg" | "video/mp4" | ...


class StockProvider(Protocol):
    name: str

    def availability(self) -> ProviderAvailabilityStatus:
        """Synchronous, cheap — just checks whether credentials are
        configured. Does NOT make a network call (that's what
        `search` failing would tell you, as TEMPORARILY_UNAVAILABLE/
        RATE_LIMITED/FAILED via orchestration/provider_health.py)."""
        ...

    async def search(self, *, query: str, kind: str, orientation: str | None = None, max_results: int = 5) -> list[StockCandidate]:
        """`kind` is "image" or "video". Raises on a real network/API
        failure (caller — asset_router.py — classifies and records it
        via provider_health.py); returns an empty list for a
        legitimate "no results" response, which is not a failure."""
        ...
