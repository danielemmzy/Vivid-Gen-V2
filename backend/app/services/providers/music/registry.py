from app.services.providers.music.base import MusicProvider
from app.services.providers.music.freesound import FreesoundMusicProvider

_MUSIC_PROVIDERS: dict[str, type] = {"freesound": FreesoundMusicProvider}


def get_music_provider(name: str = "freesound") -> MusicProvider:
    cls = _MUSIC_PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown music provider: {name}")
    return cls()


def list_music_providers() -> list[MusicProvider]:
    return [cls() for cls in _MUSIC_PROVIDERS.values()]
