"""V2 Phase 19: Podcast/Audio -> Video (spec §43).

Real transcription step (via the configured TranscriptionProvider —
openai_whisper by default), then hands the transcript to the Director as
source_facts so scene visuals are grounded in what was actually said
rather than invented. The "3/5/10 Shorts" extraction spec §43 also
mentions is the SAME highlight-detection pipeline as workflows/shorts.py
— call that separately after this workflow's main video exists, don't
duplicate the logic here.
"""
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from app.services.providers.audio.registry import get_transcription_provider
from app.services.storage.s3 import download_to_path


class PodcastRequest(BaseModel):
    audio_s3_key: str
    duration_seconds: int = Field(default=120, ge=30, le=600)
    style: str | None = None
    language: str = "en"


async def build_plan_inputs(body: PodcastRequest) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = str(Path(tmpdir) / "audio")
        download_to_path(body.audio_s3_key, local_path)
        provider = get_transcription_provider()
        segments = await provider.transcribe(audio_path=local_path)

    transcript_text = " ".join(s["text"] for s in segments)
    return {
        "prompt": f"Create a {body.duration_seconds}-second video version of this podcast/audio content.",
        "project_type": "podcast",
        "duration_seconds": body.duration_seconds,
        "style": body.style,
        "language": body.language,
        "source_facts": transcript_text[:15000],
    }
