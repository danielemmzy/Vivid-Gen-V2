"""TranscriptionProvider using OpenAI's Whisper API (REST, via httpx — no
SDK dependency needed for one multipart upload). Used for: caption
generation from a voiceover/video's audio (spec §48), and the transcript
step in the Shorts/URL-workflows (spec §36-§37).

NOT verified against a real OpenAI account in this session. Response
shape (`verbose_json` with `segments: [{start, end, text}, ...]`) matches
OpenAI's publicly documented Whisper API as of this codebase's training
data — confirm against current docs before relying on it.
"""
import httpx

from app.core.config import settings
from app.core.exceptions import VividGenError


class TranscriptionError(VividGenError):
    http_status = 502
    code = "TRANSCRIPTION_FAILED"


class OpenAIWhisperProvider:
    name = "openai_whisper"

    async def transcribe(self, *, audio_path: str) -> list[dict]:
        if not settings.openai_api_key:
            raise TranscriptionError("Transcription is not configured", details={"missing": "OPENAI_API_KEY"})

        async with httpx.AsyncClient(timeout=120) as client:
            with open(audio_path, "rb") as f:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    files={"file": f},
                    data={"model": "whisper-1", "response_format": "verbose_json"},
                )
            if response.status_code != 200:
                raise TranscriptionError("Whisper request failed", details={"status": response.status_code, "body": response.text[:500]})
            body = response.json()

        return [
            {"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
            for seg in body.get("segments", [])
        ]
