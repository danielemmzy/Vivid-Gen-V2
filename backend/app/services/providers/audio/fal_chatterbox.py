"""Managed fal.ai Chatterbox TTS with optional reference-audio voice cloning.

The reference sample is passed to fal as a short-lived signed URL. The key remains
server-side and the sample is never exposed as a public URL in the project plan.
"""
import asyncio

import fal_client
import httpx

from app.core.config import settings
from app.services.providers.audio.base import TTSSynthesisError


class FalChatterboxTTSProvider:
    name = "fal_chatterbox"

    async def synthesize(
        self, *, text: str, voice_id: str | None, style: str | None, output_path: str,
        reference_audio_url: str | None = None,
    ) -> float:
        if not settings.fal_key:
            raise TTSSynthesisError("fal Chatterbox is not configured", details={"missing": "FAL_KEY"})
        if not text.strip():
            raise TTSSynthesisError("Chatterbox text must not be empty")
        # Chatterbox's API accepts a reference audio URL, not a named voice ID.
        # Style presets map to supported expressiveness controls rather than being silently ignored.
        style_text = (style or "").lower()
        exaggeration = 0.25
        if any(term in style_text for term in ("cinematic", "expressive", "dramatic")):
            exaggeration = 0.48
        elif any(term in style_text for term in ("energetic", "upbeat", "promotional")):
            exaggeration = 0.55
        elif any(term in style_text for term in ("calm", "gentle", "warm", "reassuring")):
            exaggeration = 0.18
        arguments: dict = {"text": text[:5000], "exaggeration": exaggeration, "temperature": 0.7, "cfg": 0.5}
        if reference_audio_url:
            arguments["audio_url"] = reference_audio_url

        def _run() -> dict:
            return fal_client.subscribe("fal-ai/chatterbox/text-to-speech", arguments=arguments)

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_run), timeout=settings.chatterbox_tts_timeout_seconds)
        except Exception as exc:  # provider SDK has provider-specific exception types
            raise TTSSynthesisError("fal Chatterbox request failed", details={"cause": str(exc)[:500]}) from exc
        audio = (result or {}).get("audio")
        audio_url = audio if isinstance(audio, str) else (audio or {}).get("url")
        if not audio_url:
            raise TTSSynthesisError("fal Chatterbox response did not include audio", details={"keys": list((result or {}).keys())})
        try:
            async with httpx.AsyncClient(timeout=settings.chatterbox_tts_timeout_seconds, follow_redirects=True) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                if not response.content:
                    raise TTSSynthesisError("fal Chatterbox returned an empty audio file")
                with open(output_path, "wb") as target:
                    target.write(response.content)
            from app.services.media.ffmpeg import probe_duration_seconds
            duration = await probe_duration_seconds(output_path)
        except TTSSynthesisError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TTSSynthesisError("fal Chatterbox audio could not be downloaded or decoded", details={"cause": str(exc)[:400]}) from exc
        if duration <= 0:
            raise TTSSynthesisError("fal Chatterbox returned zero-length audio")
        return duration
