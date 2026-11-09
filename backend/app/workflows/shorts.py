"""V2 Phase 15 (spec §36-§37): Video -> Shorts.

Does NOT go through orchestration/planner.py or executor.py — those plan
and generate NEW footage; this selects and reframes clips from footage
that already exists. Pipeline, all real (no stub steps): download source
video -> transcribe (TranscriptionProvider) -> highlight detection
(orchestration/highlights.py, a separate smaller LLM call) -> for each
candidate, trim + center-crop to 9:16 (services/media/ffmpeg.py's
`trim_and_reframe_clip`) -> upload each as an Asset row.

NOT implemented: burning captions onto each Short automatically (the
primitive exists — `ffmpeg.burn_captions` — but wiring per-clip caption
timing from the original transcript into each trimmed clip's own
timeline needs timestamp-offset math this pass didn't do) and reusing an
already-existing Asset if `repurpose.py` calls this on a video that's
already been transcribed before (currently re-transcribes every time,
which is correct but wasteful if called twice on the same source).
"""
import tempfile
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asset import Asset
from app.orchestration.highlights import detect_highlights
from app.services.media.ffmpeg import trim_and_reframe_clip
from app.services.providers.audio.registry import get_transcription_provider
from app.services.storage.s3 import download_to_path, upload_from_path

logger = get_logger(__name__)


class ShortsRequest(BaseModel):
    source_video_s3_key: str
    max_clips: int = Field(default=5, ge=1, le=10)


async def generate_shorts(session: AsyncSession, user_id: str, project_id: str, body: ShortsRequest) -> list[Asset]:
    with tempfile.TemporaryDirectory() as tmpdir:
        source_local = str(Path(tmpdir) / "source.mp4")
        download_to_path(body.source_video_s3_key, source_local)

        # Whisper (the default transcription provider) transcribes audio
        # files; most video containers work fine passed directly to it, so
        # no separate audio-extraction step here — if that turns out not
        # to hold for a given container/codec, extract audio with ffmpeg
        # first (not needed for the common mp4/aac case).
        provider = get_transcription_provider()
        segments = await provider.transcribe(audio_path=source_local)
        if not segments:
            logger.warning("shorts_no_transcript", project_id=project_id)
            return []

        highlight_plan = await detect_highlights(transcript_segments=segments, max_candidates=body.max_clips)

        assets: list[Asset] = []
        for candidate in highlight_plan.candidates:
            clip_local = str(tmp_path := Path(tmpdir) / f"short_{uuid4().hex}.mp4")
            await trim_and_reframe_clip(
                source_local, str(tmp_path),
                start_seconds=candidate.start_seconds, end_seconds=candidate.end_seconds,
            )
            output_key = f"generations/{user_id}/projects/{project_id}/shorts/{uuid4().hex}.mp4"
            upload_from_path(clip_local, output_key, "video/mp4")

            asset = Asset(
                id="asset_" + uuid4().hex, project_id=project_id, user_id=user_id, type="video",
                source="render", s3_key=output_key,
                duration_seconds=candidate.end_seconds - candidate.start_seconds,
                asset_metadata={"reason": candidate.reason, "hook_score": candidate.hook_score, "kind": "short"},
            )
            session.add(asset)
            assets.append(asset)

        await session.commit()
        logger.info("shorts_generated", project_id=project_id, count=len(assets))
        return assets
