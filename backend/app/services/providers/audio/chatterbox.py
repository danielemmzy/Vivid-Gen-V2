"""Chatterbox TTS adapter.

Supports two explicit server contracts:
- ``openai_compatible``: POST /v1/audio/speech with ``input`` and ``voice``.
- ``modal_query``: the official Modal example shape, POST the configured endpoint
  with a ``prompt`` query parameter and a binary audio response.

Chatterbox model weights live in the separately deployed inference service, not
in the web/API container. This adapter fails closed when it is not configured;
it never silently switches providers.
"""
import httpx

from app.core.config import settings
from app.services.providers.audio.base import TTSSynthesisError


class ChatterboxTTSProvider:
    name = "chatterbox"

    async def synthesize(self, *, text: str, voice_id: str | None, style: str | None, output_path: str, reference_audio_url: str | None = None) -> float:
        endpoint = settings.chatterbox_tts_base_url.strip()
        if not endpoint:
            raise TTSSynthesisError("Chatterbox is not configured", details={"missing": "CHATTERBOX_TTS_BASE_URL"})
        if not text.strip():
            raise TTSSynthesisError("Chatterbox text must not be empty")

        headers: dict[str, str] = {}
        if settings.chatterbox_tts_api_key:
            headers["Authorization"] = f"Bearer {settings.chatterbox_tts_api_key}"

        mode = settings.chatterbox_tts_mode.strip().lower()
        if mode == "modal_query":
            if voice_id:
                raise TTSSynthesisError(
                    "The configured Chatterbox Modal endpoint does not accept a voice_id; use an OpenAI-compatible endpoint for voice selection",
                    details={"mode": mode},
                )
            url = endpoint
            params = {"prompt": text}
            body = None
        elif mode == "openai_compatible":
            url = endpoint.rstrip("/")
            if not url.endswith("/v1/audio/speech"):
                url += "/v1/audio/speech"
            params = None
            body = {"model": "chatterbox", "input": text, "voice": voice_id or "default", "response_format": "wav"}
        else:
            raise TTSSynthesisError("Unsupported Chatterbox endpoint mode", details={"mode": mode})

        try:
            async with httpx.AsyncClient(timeout=settings.chatterbox_tts_timeout_seconds) as client:
                response = await client.post(url, params=params, json=body, headers=headers)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if not response.content or "application/json" in content_type:
                    detail = response.text[:300] if response.content else "empty response"
                    raise TTSSynthesisError("Chatterbox returned no audio bytes", details={"content_type": content_type, "response": detail})
                with open(output_path, "wb") as target:
                    target.write(response.content)
        except TTSSynthesisError:
            raise
        except Exception as exc:  # noqa: BLE001 - endpoint clients expose different network exceptions
            raise TTSSynthesisError("Chatterbox TTS request failed", details={"cause": str(exc)[:500]}) from exc

        from app.services.media.ffmpeg import probe_duration_seconds
        try:
            duration = await probe_duration_seconds(output_path)
        except Exception as exc:  # noqa: BLE001 - reject HTML/error bodies saved as audio
            raise TTSSynthesisError("Chatterbox response could not be decoded as audio", details={"cause": str(exc)[:300]}) from exc
        if duration <= 0:
            raise TTSSynthesisError("Chatterbox returned a zero-length audio file")
        return duration
