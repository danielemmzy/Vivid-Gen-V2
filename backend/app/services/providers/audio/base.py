"""Provider-neutral contracts for speech synthesis and transcription.

Prompt-to-audio music/ambience generation has its own AudioGenerationProvider
contract in generation_base.py; licensed sound search remains in providers/music.
"""
from typing import Protocol

from app.core.exceptions import VividGenError


class TTSSynthesisError(VividGenError):
    http_status = 502
    code = "TTS_SYNTHESIS_FAILED"


class TTSProvider(Protocol):
    async def synthesize(self, *, text: str, voice_id: str | None, style: str | None, output_path: str, reference_audio_url: str | None = None) -> float:
        """Writes synthesized speech to `output_path`. Returns duration in seconds."""
        ...


class TranscriptionProvider(Protocol):
    async def transcribe(self, *, audio_path: str) -> list[dict]:
        """Returns caption segments: [{"start": float, "end": float, "text": str}, ...]."""
        ...
