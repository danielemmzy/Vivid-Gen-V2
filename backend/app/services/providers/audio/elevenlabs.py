"""Alternative TTSProvider using ElevenLabs' REST API directly (httpx,
already a dependency — no new SDK needed for a single REST call). Not the
default (see fal_tts.py for why fal is default) — this exists so voice
quality can be upgraded per spec §46's "don't depend on one voice
provider" without changing any calling code, since both implement the
same TTSProvider Protocol.

NOT verified against a real ElevenLabs account in this session — no API
key available in this sandbox. The endpoint path and response handling
follow ElevenLabs' publicly documented text-to-speech API shape as of
this codebase's training data; confirm against their current docs before
relying on this in production.
"""
import httpx

from app.core.config import settings
from app.services.providers.audio.base import TTSSynthesisError

_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs' public "Rachel" voice, used only if none is specified


class ElevenLabsTTSProvider:
    name = "elevenlabs"

    async def synthesize(self, *, text: str, voice_id: str | None, style: str | None, output_path: str, reference_audio_url: str | None = None) -> float:
        if not settings.elevenlabs_api_key:
            raise TTSSynthesisError("ElevenLabs is not configured", details={"missing": "ELEVENLABS_API_KEY"})

        voice = voice_id or _DEFAULT_VOICE_ID
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={"xi-api-key": settings.elevenlabs_api_key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2"},
            )
            if response.status_code != 200:
                raise TTSSynthesisError("ElevenLabs request failed", details={"status": response.status_code, "body": response.text[:500]})
            with open(output_path, "wb") as f:
                f.write(response.content)

        from app.services.media.ffmpeg import probe_duration_seconds
        return await probe_duration_seconds(output_path)
