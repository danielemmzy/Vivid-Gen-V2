from app.core.config import settings
from app.services.providers.audio.base import TranscriptionProvider, TTSProvider
from app.services.providers.audio.chatterbox import ChatterboxTTSProvider
from app.services.providers.audio.elevenlabs import ElevenLabsTTSProvider
from app.services.providers.audio.fal_tts import FalTTSProvider
from app.services.providers.audio.fal_chatterbox import FalChatterboxTTSProvider
from app.services.providers.audio.openai_whisper import OpenAIWhisperProvider

_TTS_PROVIDERS: dict[str, type[TTSProvider]] = {"fal": FalTTSProvider, "elevenlabs": ElevenLabsTTSProvider, "chatterbox": ChatterboxTTSProvider, "fal_chatterbox": FalChatterboxTTSProvider}
_TRANSCRIPTION_PROVIDERS: dict[str, type[TranscriptionProvider]] = {"openai_whisper": OpenAIWhisperProvider}


def get_tts_provider(name: str | None = None) -> TTSProvider:
    resolved = name or settings.tts_provider
    cls = _TTS_PROVIDERS.get(resolved)
    if cls is None:
        raise ValueError(f"Unknown TTS provider: {resolved}")
    return cls()


def get_transcription_provider(name: str | None = None) -> TranscriptionProvider:
    resolved = name or settings.transcription_provider
    cls = _TRANSCRIPTION_PROVIDERS.get(resolved)
    if cls is None:
        raise ValueError(f"Unknown transcription provider: {resolved}")
    return cls()
