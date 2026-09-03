"""ffmpeg/ffprobe wrappers. All calls run in a worker thread since they're
blocking subprocess calls — never call these from an async route handler
directly, only from worker jobs (jobs/media.py), which already run off
the request path."""
import asyncio
import json
import subprocess

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class FfmpegError(RuntimeError):
    pass


async def probe_duration_seconds(local_path: str) -> float:
    def _run() -> float:
        result = subprocess.run(
            [settings.ffprobe_bin, "-v", "error", "-show_entries", "format=duration", "-of", "json", local_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:500])
        return float(json.loads(result.stdout)["format"]["duration"])

    return await asyncio.to_thread(_run)


async def generate_thumbnail(video_path: str, output_path: str, *, at_seconds: float = 0.5) -> None:
    def _run() -> None:
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-ss", str(at_seconds), "-i", video_path, "-frames:v", "1", "-q:v", "3", output_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:500])

    await asyncio.to_thread(_run)


async def concat_clips(clip_paths: list[str], output_path: str) -> None:
    """Concatenate shots into a finished movie via ffmpeg's concat demuxer.
    Assumes clips already share codec/resolution/fps (the storyboard
    feature should enforce that at generation time — mixed encodings need
    a re-encode pass here instead of stream copy, which is slower but more
    robust; swap `-c copy` for `-c:v libx264 -c:a aac` if clips ever come
    from mixed models/resolutions)."""
    if not clip_paths:
        raise FfmpegError("No clips to assemble")

    def _run() -> None:
        list_file = f"{output_path}.txt"
        with open(list_file, "w") as f:
            for path in clip_paths:
                f.write(f"file '{path}'\n")
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", output_path],
            capture_output=True, text=True, timeout=settings.movie_assembly_max_seconds,
        )
        if result.returncode != 0:
            # Fall back to a re-encode pass — mismatched clip parameters is
            # the most common cause of a plain stream-copy concat failing.
            result2 = subprocess.run(
                [settings.ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                 "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", output_path],
                capture_output=True, text=True, timeout=settings.movie_assembly_max_seconds,
            )
            if result2.returncode != 0:
                raise FfmpegError(result2.stderr[:800])

    await asyncio.to_thread(_run)
