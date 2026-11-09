"""Round 4, decision #4 (confirmed): a real Music Router needs a real
search provider, not just BrandKit.default_music_s3_key. This is the
interface; `freesound.py` is the concrete adapter. BrandKit's default
track becomes ONE candidate the Music Router considers (see
orchestration/audio_router.py), not the hard-coded only option.
"""
from dataclasses import dataclass
from typing import Protocol

from app.core.constants import ProviderAvailabilityStatus


@dataclass
class MusicCandidate:
    external_id: str
    name: str
    url: str                 # downloadable preview/file URL
    duration_seconds: float | None
    license: str              # e.g. a Creative Commons license URL/name — preserved verbatim, never dropped
    attribution: str
    tags: list[str]


class MusicProvider(Protocol):
    name: str

    def availability(self) -> ProviderAvailabilityStatus:
        ...

    async def search(self, *, query: str, max_duration_seconds: float | None = None, max_results: int = 5) -> list[MusicCandidate]:
        """Raises on a real network/API failure; returns an empty list
        for a legitimate "no results" response."""
        ...
