"""Default TTSProvider: reuses fal's already-integrated `tts-voice-clone`
model (see providers/fal/catalog.py) via `fal_client.subscribe`, which
blocks until the result is ready — appropriate here since this runs
inside a background render job (renderer.py), not a web request, and a
voiceover line is seconds of audio, not minutes like video. This is the
default (`TTS_PROVIDER=fal`) specifically so voiceover works with the
same FAL_KEY the rest of the app already needs, no new credential
required for the common case.
"""
import asyncio

import fal_client
import httpx

from app.core.config import settings
from app.services.providers.fal.catalog import get_model
from app.services.providers.audio.base import TTSSynthesisError


class FalTTSProvider:
    name = "fal"

    async def synthesize(self, *, text: str, voice_id: str | None, style: str | None, output_path: str, reference_audio_url: str | None = None) -> float:
        model = get_model("tts-voice-clone")
        arguments: dict = {"text": text}
        if voice_id:
            arguments["voice_id"] = voice_id
        if style:
            arguments["style"] = style

        def _run() -> dict:
            return fal_client.subscribe(model["provider_model_id"], arguments=arguments)

        try:
            result = await asyncio.to_thread(_run)
        except Exception as exc:  # noqa: BLE001 — fal_client raises a mix of error types
            raise TTSSynthesisError("fal TTS request failed", details={"cause": str(exc)}) from exc

        audio_url = (result or {}).get("audio", {}).get("url") or (result or {}).get("audio_url")
        if not audio_url:
            raise TTSSynthesisError("fal TTS response had no audio URL", details={"raw_keys": list((result or {}).keys())})

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(audio_url)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)

        from app.services.media.ffmpeg import probe_duration_seconds
        return await probe_duration_seconds(output_path)
