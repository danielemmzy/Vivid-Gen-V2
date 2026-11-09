from app.core.config import settings
from app.services.providers.audio.fal_audio_generation import FalAudioGenerationProvider
from app.services.providers.audio.generation_base import AudioGenerationProvider

_AUDIO_GENERATION_PROVIDERS: dict[str, type] = {"fal": FalAudioGenerationProvider}


def get_audio_generation_provider(name: str | None = None) -> AudioGenerationProvider:
    resolved = (name or settings.audio_generation_provider).strip().lower()
    provider_cls = _AUDIO_GENERATION_PROVIDERS.get(resolved)
    if provider_cls is None:
        raise ValueError(f"Unknown audio generation provider: {resolved}")
    return provider_cls()


def list_audio_generation_providers() -> list[str]:
    return sorted(_AUDIO_GENERATION_PROVIDERS)
