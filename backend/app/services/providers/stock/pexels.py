"""Round 4, decision #1 (confirmed): a real adapter against Pexels'
documented API — https://www.pexels.com/api/documentation/. Not
tested against the live API in this session (no network access in this
sandbox, verified directly — see the round-3/4 reports for that
constraint) — implemented from the documented request/response shape,
not guessed. If `settings.pexels_api_key` is absent, `availability()`
returns NOT_CONFIGURED and `search()` raises `ProviderNotConfiguredError`
immediately, before any network call — a missing key is never allowed
to look like a failed search.

Pexels license: every photo/video is free to use under the Pexels
License (https://www.pexels.com/license/) — attribution is appreciated,
not legally required, but is still recorded (photographer/creator name +
the page URL) since the round-4 brief explicitly asked for provenance to
be preserved regardless of whether the license mandates it.
"""
import httpx

from app.core.config import settings
from app.core.constants import ProviderAvailabilityStatus
from app.core.exceptions import ProviderNotConfiguredError
from app.services.providers.stock.base import StockCandidate

_PHOTO_SEARCH_URL = "https://api.pexels.com/v1/search"
_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"


class PexelsStockProvider:
    name = "pexels"

    def availability(self) -> ProviderAvailabilityStatus:
        if not settings.pexels_api_key:
            return ProviderAvailabilityStatus.NOT_CONFIGURED
        return ProviderAvailabilityStatus.AVAILABLE

    async def search(self, *, query: str, kind: str, orientation: str | None = None, max_results: int = 5) -> list[StockCandidate]:
        if not settings.pexels_api_key:
            raise ProviderNotConfiguredError("PEXELS_API_KEY is not configured", details={"provider": "pexels"})

        headers = {"Authorization": settings.pexels_api_key}
        params: dict = {"query": query, "per_page": min(max_results, 15)}
        if orientation:
            params["orientation"] = orientation

        url = _PHOTO_SEARCH_URL if kind == "image" else _VIDEO_SEARCH_URL
        async with httpx.AsyncClient(timeout=settings.stock_provider_timeout_seconds) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()

        if kind == "image":
            return [item for p in payload.get("photos", []) if (item := self._map_photo(p)).url and item.preview_url]
        return [item for v in payload.get("videos", []) if (item := self._map_video(v)).url and item.preview_url]

    def _map_photo(self, photo: dict) -> StockCandidate:
        src = photo.get("src", {})
        return StockCandidate(
            external_id=str(photo["id"]),
            url=src.get("original") or src.get("large2x") or src.get("large"),
            preview_url=src.get("medium"),
            width=photo.get("width"),
            height=photo.get("height"),
            duration_seconds=None,
            license="pexels",
            attribution=f"Photo by {photo.get('photographer', 'unknown')} on Pexels ({photo.get('url', '')})",
            content_type="image/jpeg",
        )

    def _map_video(self, video: dict) -> StockCandidate:
        files = [f for f in video.get("video_files", []) if f.get("link")]
        files = sorted(files, key=lambda f: (f.get("width") or 0), reverse=True)
        best = files[0] if files else {}
        pictures = video.get("video_pictures", [])
        user = video.get("user", {})
        return StockCandidate(
            external_id=str(video["id"]),
            url=best.get("link", ""),
            preview_url=pictures[0].get("picture") if pictures else None,
            width=best.get("width") or video.get("width"),
            height=best.get("height") or video.get("height"),
            duration_seconds=float(video.get("duration")) if video.get("duration") else None,
            license="pexels",
            attribution=f"Video by {user.get('name', 'unknown')} on Pexels ({video.get('url', '')})",
            content_type="video/mp4",
        )
