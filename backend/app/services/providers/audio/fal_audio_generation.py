"""fal.ai text-to-audio adapter for optional music and ambience beds.

Model IDs are configurable because provider catalogs evolve. The defaults use
fal's documented Stable Audio 2.5 endpoint for music and MMAudio V2 for
short ambience/sound-design beds. Generation runs in a background worker.
"""
import asyncio

import fal_client
import httpx

from app.core.config import settings
from app.services.providers.audio.base import TTSSynthesisError
from app.services.providers.audio.generation_base import AudioRole


class FalAudioGenerationProvider:
    name = "fal"

    async def generate(self, *, prompt: str, duration_seconds: int, role: AudioRole, output_path: str) -> float:
        if not settings.fal_key:
            raise TTSSynthesisError("fal audio generation is not configured", details={"missing": "FAL_KEY"})
        if not prompt.strip():
            raise TTSSynthesisError("Audio generation prompt must not be empty")
        model_id = settings.fal_audio_music_model if role == "music" else settings.fal_audio_ambience_model
        # Stable Audio supports long-form prompt-to-audio (seconds_total); MMAudio
        # is useful for shorter sound-design clips and uses its own `duration` field.
        is_mmaudio = "mmaudio" in model_id.lower()
        duration = max(1, min(int(duration_seconds), 30 if is_mmaudio else 180))
        if is_mmaudio:
            arguments = {"prompt": prompt, "duration": float(duration)}
        else:
            arguments = {"prompt": prompt, "seconds_total": duration}

        def _run() -> dict:
            return fal_client.subscribe(model_id, arguments=arguments)

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_run), timeout=settings.audio_generation_timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - fal client has provider-specific exception classes
            raise TTSSynthesisError("fal audio generation failed", details={"model": model_id, "cause": str(exc)[:500]}) from exc

        audio_value = (result or {}).get("audio")
        audio_url = audio_value if isinstance(audio_value, str) else (audio_value or {}).get("url")
        audio_url = audio_url or (result or {}).get("audio_url") or ((result or {}).get("audio_file") or {}).get("url")
        if not audio_url:
            raise TTSSynthesisError("fal audio response did not contain an audio URL", details={"model": model_id, "keys": list((result or {}).keys())})

        try:
            async with httpx.AsyncClient(timeout=settings.audio_generation_timeout_seconds, follow_redirects=True) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                if not response.content:
                    raise TTSSynthesisError("fal audio URL returned an empty file", details={"model": model_id})
                with open(output_path, "wb") as target:
                    target.write(response.content)
        except TTSSynthesisError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TTSSynthesisError("Could not download fal audio output", details={"cause": str(exc)[:500]}) from exc

        from app.services.media.ffmpeg import probe_duration_seconds
        try:
            measured = await probe_duration_seconds(output_path)
        except Exception as exc:  # noqa: BLE001
            raise TTSSynthesisError("fal returned an undecodable audio file", details={"cause": str(exc)[:300]}) from exc
        if measured <= 0:
            raise TTSSynthesisError("fal returned zero-length audio")
        return measured
