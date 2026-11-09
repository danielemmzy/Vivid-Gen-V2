"""Round 4, decision #4 (confirmed): a real adapter against Freesound's
documented API — https://freesound.org/docs/api/. Not tested against the
live API in this session (no network access in this sandbox — see the
round-3/4 reports). If `settings.freesound_api_key` is absent,
`availability()` returns NOT_CONFIGURED and `search()` raises
`ProviderNotConfiguredError` before any network call.

Freesound license metadata is preserved VERBATIM as the license URL
Freesound itself returns (e.g. "http://creativecommons.org/licenses/by/4.0/")
rather than normalized/guessed into a short code — the round-4 brief
specifically called out keeping real licensing metadata, and a license
URL is the only thing that's actually unambiguous.
"""
import httpx

from app.core.config import settings
from app.core.constants import ProviderAvailabilityStatus
from app.core.exceptions import ProviderNotConfiguredError
from app.services.providers.music.base import MusicCandidate

_SEARCH_URL = "https://freesound.org/apiv2/search/text/"


class FreesoundMusicProvider:
    name = "freesound"

    def availability(self) -> ProviderAvailabilityStatus:
        if not settings.freesound_api_key:
            return ProviderAvailabilityStatus.NOT_CONFIGURED
        return ProviderAvailabilityStatus.AVAILABLE

    async def search(self, *, query: str, max_duration_seconds: float | None = None, max_results: int = 5) -> list[MusicCandidate]:
        if not settings.freesound_api_key:
            raise ProviderNotConfiguredError("FREESOUND_API_KEY is not configured", details={"provider": "freesound"})

        filter_parts = ["duration:[1 TO *]"]
        if max_duration_seconds:
            filter_parts = [f"duration:[1 TO {int(max_duration_seconds)}]"]
        params = {
            "query": query,
            "token": settings.freesound_api_key,
            "fields": "id,name,previews,license,username,duration,tags,url",
            "filter": " ".join(filter_parts),
            "page_size": min(max_results, 15),
        }

        async with httpx.AsyncClient(timeout=settings.music_provider_timeout_seconds) as client:
            response = await client.get(_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        return [self._map_result(r) for r in payload.get("results", [])]

    def _map_result(self, result: dict) -> MusicCandidate:
        previews = result.get("previews", {})
        url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3") or ""
        return MusicCandidate(
            external_id=str(result["id"]),
            name=result.get("name", "untitled"),
            url=url,
            duration_seconds=float(result["duration"]) if result.get("duration") else None,
            license=result.get("license", "unknown"),
            attribution=f"\"{result.get('name', 'untitled')}\" by {result.get('username', 'unknown')} (freesound.org) — {result.get('license', 'unknown')}",
            tags=result.get("tags", []),
        )
