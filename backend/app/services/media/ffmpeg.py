"""ffmpeg/ffprobe wrappers. All calls run in a worker thread since they're
blocking subprocess calls — never call these from an async route handler
directly, only from worker jobs (jobs/production.py's run_render_task and
friends), which already run off the request path."""
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




async def probe_has_audio_stream(media_path: str) -> bool:
    """Return whether ffprobe finds an audio stream in a media file."""
    def _run() -> bool:
        result = subprocess.run(
            [settings.ffprobe_bin, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "json", media_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:500])
        return bool(json.loads(result.stdout).get("streams"))
    return await asyncio.to_thread(_run)


async def normalize_audio_file(source_path: str, output_path: str) -> float:
    """Normalize provider output to a broadly playable stereo MP3 timeline asset."""
    def _run() -> None:
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-i", source_path, "-vn", "-ac", "2", "-ar", "48000",
             "-c:a", "libmp3lame", "-b:a", "192k", "-write_xing", "1", output_path],
            capture_output=True, text=True, timeout=settings.movie_assembly_max_seconds,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])
    await asyncio.to_thread(_run)
    return await probe_duration_seconds(output_path)


async def probe_video_dimensions(video_path: str) -> tuple[int, int]:
    """Return the first video stream's width and height using ffprobe."""
    def _run() -> tuple[int, int]:
        result = subprocess.run(
            [settings.ffprobe_bin, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", video_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:500])
        streams = json.loads(result.stdout).get("streams") or []
        if not streams or not streams[0].get("width") or not streams[0].get("height"):
            raise FfmpegError("Could not read video dimensions")
        return int(streams[0]["width"]), int(streams[0]["height"])

    return await asyncio.to_thread(_run)


async def resize_video_to_output_resolution(video_path: str, output_path: str, *, resolution: str) -> bool:
    """Normalize the final clip's short edge to 420p or 720p.

    Returns False when the video already matches the requested target. The
    operation preserves the source aspect ratio, scales landscape by height
    and portrait by width, and re-encodes to a broadly playable H.264/AAC MP4.
    This is an export-size operation; it does not alter provider generation
    parameters or imply lower provider GPU charges.
    """
    targets = {"420p": 420, "720p": 720}
    target = targets.get(resolution)
    if target is None:
        raise FfmpegError(f"Unsupported output resolution: {resolution}")

    width, height = await probe_video_dimensions(video_path)
    if min(width, height) == target and width % 2 == 0 and height % 2 == 0:
        return False

    # Quote each if-expression so ffmpeg's filter parser treats commas as
    # expression syntax rather than filter-chain separators. -2 preserves
    # aspect ratio and rounds the computed dimension to an even integer.
    scale_filter = (
        f"scale=w='if(gte(iw,ih),-2,{target})':"
        f"h='if(gte(iw,ih),{target},-2)':flags=lanczos"
    )

    def _run() -> None:
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-i", video_path,
             "-map", "0:v:0", "-map", "0:a?", "-vf", scale_filter,
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", output_path],
            capture_output=True, text=True, timeout=settings.movie_assembly_max_seconds,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

    await asyncio.to_thread(_run)
    return True


async def generate_thumbnail(video_path: str, output_path: str, *, at_seconds: float = 0.5) -> None:
    def _run() -> None:
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-ss", str(at_seconds), "-i", video_path, "-frames:v", "1", "-q:v", "3", output_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:500])

    await asyncio.to_thread(_run)


async def trim_video_to_duration(video_path: str, output_path: str, *, duration_seconds: float) -> None:
    """Create a normalized clip with an exact usable timeline duration.

    This is used when a model can only generate (for example) 5 seconds but
    the movie planner needs the final shot to contribute only 2.5 seconds.
    The provider output is preserved in storage; only the render copy is trimmed.
    """
    if duration_seconds <= 0:
        raise FfmpegError("Timeline clip duration must be positive")

    def _run() -> None:
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-i", video_path, "-t", f"{duration_seconds:.3f}",
             "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", output_path],
            capture_output=True, text=True, timeout=settings.movie_assembly_max_seconds,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

    await asyncio.to_thread(_run)


async def probe_has_audio(video_path: str) -> bool:
    """Return whether a media file contains an audio stream."""
    def _run() -> bool:
        result = subprocess.run(
            [settings.ffprobe_bin, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_type", "-of", "json", video_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:500])
        return bool(json.loads(result.stdout).get("streams"))
    return await asyncio.to_thread(_run)


async def normalize_clip_for_assembly(
    video_path: str, output_path: str, *, width: int, height: int,
    frame_rate: int = 24, duration_seconds: float | None = None,
    source_start_seconds: float = 0.0, source_volume: float = 1.0, source_muted: bool = False,
) -> float:
    """Normalize one clip to the shared movie canvas, codec, fps and audio layout.

    Every clip gets H.264/AAC, even dimensions, a fixed frame rate and a stereo
    audio stream (silence when the source has none). This prevents concat
    demuxer failures when a movie mixes providers, uploaded footage and silent
    Wan clips. The returned duration is the intended normalized duration.
    """
    if width < 2 or height < 2 or width % 2 or height % 2 or frame_rate < 1:
        raise FfmpegError("Assembly canvas must use positive even dimensions and a positive frame rate")
    source_duration = await probe_duration_seconds(video_path)
    source_start = max(0.0, float(source_start_seconds))
    duration = float(duration_seconds) if duration_seconds is not None else max(0.05, source_duration - source_start)
    if duration <= 0:
        raise FfmpegError("Assembly clip duration must be positive")
    has_audio = await probe_has_audio(video_path)
    video_filter = (
        f"tpad=stop_mode=clone:stop_duration={duration:.3f},"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={frame_rate}"
    )

    def _run() -> None:
        cmd = [settings.ffmpeg_bin, "-y"]
        if source_start > 0:
            cmd.extend(["-ss", f"{source_start:.3f}"])
        cmd.extend(["-i", video_path])
        if not has_audio:
            cmd.extend(["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        cmd.extend(["-map", "0:v:0", "-vf", video_filter])
        if has_audio:
            volume = 0.0 if source_muted else max(0.0, min(float(source_volume), 4.0))
            cmd.extend(["-map", "0:a:0", "-af", f"volume={volume:.4f},apad=whole_dur={duration:.3f}"])
        else:
            cmd.extend(["-map", "1:a:0"])
        cmd.extend([
            "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", output_path,
        ])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=settings.movie_assembly_max_seconds)
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

    await asyncio.to_thread(_run)
    return duration


async def extract_final_frame(video_path: str, output_path: str, *, offset_from_end_seconds: float = 0.15) -> None:
    """Extract a JPEG from near the end of a clip for continuity conditioning."""
    offset = max(0.02, min(float(offset_from_end_seconds), 2.0))

    def _run() -> None:
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-sseof", f"-{offset:.3f}", "-i", video_path,
             "-map", "0:v:0", "-frames:v", "1", "-q:v", "2", output_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

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


# --- render pipeline primitives (used by services/media/renderer.py and
# jobs/production.py's run_render_task) ---
#
# The core trim/concat/audio-pad/normalization filter graphs have been
# exercised with synthetic FFmpeg clips in the implementation workspace.
# Provider-generated samples and production-specific fonts/overlays still
# need a live acceptance run before deployment sign-off.


# gap-closure (0006): removed `mix_audio_over_video` and
# `replace_audio_track` — both were confirmed to have zero callers
# anywhere in the codebase (per-scene audio now goes through
# `compose_audio_timeline` below, and the "Audio Replace" generation type
# is a remote provider call — services/generation/service.py:384 — not a
# local ffmpeg operation). Leaving unused ffmpeg helpers in place would
# have been exactly the kind of dead code this pass was asked to remove.


def _hex_to_ass_bgr(hex_color: str) -> str:
    """ASS/libass colors are &HBBGGRR (blue-green-red, reversed from the
    usual #RRGGBB web hex) — converts so callers (build_render_manifest.py,
    passing a BrandKit.primary_color/secondary_color like "#FFAA00") don't
    need to know that convention themselves."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "&HFFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{b}{g}{r}".upper()


async def burn_captions(
    video_path: str, srt_path: str, output_path: str, *, style: str = "minimal",
    primary_color: str | None = None, outline_color: str | None = None, font_family: str | None = None,
) -> None:
    """Burns SRT captions into the video using ffmpeg's subtitles filter.
    `style` selects a force_style string — kept intentionally simple
    (4 presets, not a full styling DSL) matching CaptionPlan.style's four
    options. `primary_color`/`outline_color`/`font_family` (gap-closure:
    wired from BrandKit — see build_render_manifest.py) override individual
    fields of whichever preset is selected, rather than requiring a whole
    new preset per brand. Requires the ffmpeg build to have libass — most
    distro/Docker ffmpeg builds do, but this hasn't been confirmed against
    this project's actual container image."""
    force_styles = {
        "minimal": "Fontsize=22,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=1,Outline=1",
        "creator": "Fontsize=28,PrimaryColour=&H00FFFF,Bold=1,BorderStyle=1,Outline=2",
        "bold": "Fontsize=32,PrimaryColour=&HFFFFFF,Bold=1,BorderStyle=3,BackColour=&H80000000",
        "corporate": "Fontsize=24,PrimaryColour=&HFFFFFF,Fontname=Arial,BorderStyle=1,Outline=1",
        "cinematic": "Fontsize=26,PrimaryColour=&HF0F0F0,Fontname=Georgia,BorderStyle=1,Outline=1,Shadow=1",
    }
    force_style = force_styles.get(style, force_styles["minimal"])
    overrides = []
    if primary_color:
        overrides.append(f"PrimaryColour={_hex_to_ass_bgr(primary_color)}")
    if outline_color:
        overrides.append(f"OutlineColour={_hex_to_ass_bgr(outline_color)}")
        overrides.append(f"BackColour={_hex_to_ass_bgr(outline_color)}")
    if font_family:
        overrides.append(f"Fontname={font_family}")
    if overrides:
        force_style = force_style + "," + ",".join(overrides)

    def _run() -> None:
        # subtitles filter needs an escaped path on some platforms (colons
        # in Windows-style paths) — not handled here since this runs in a
        # Linux container per the project's Dockerfile, not on Windows.
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-i", video_path,
             "-vf", f"subtitles={srt_path}:force_style='{force_style}'",
             "-c:a", "copy", output_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

    await asyncio.to_thread(_run)


async def overlay_image(
    video_path: str, image_path: str, output_path: str, *,
    position: str = "bottom_right", opacity: float = 0.85, margin_px: int = 24,
) -> None:
    """Overlays a logo/watermark image (BrandKit.logo_s3_key or
    watermark_s3_key) at a corner of the video."""
    positions = {
        "bottom_right": f"main_w-overlay_w-{margin_px}:main_h-overlay_h-{margin_px}",
        "bottom_left": f"{margin_px}:main_h-overlay_h-{margin_px}",
        "top_right": f"main_w-overlay_w-{margin_px}:{margin_px}",
        "top_left": f"{margin_px}:{margin_px}",
    }
    overlay_xy = positions.get(position, positions["bottom_right"])

    def _run() -> None:
        filter_complex = f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[logo];[0:v][logo]overlay={overlay_xy}"
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-i", video_path, "-i", image_path,
             "-filter_complex", filter_complex, "-c:a", "copy", output_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

    await asyncio.to_thread(_run)


# gap-closure (0006): removed `concat_audio_clips` — confirmed zero
# callers (voiceover lines are no longer concatenated into one file;
# each scene's line is its own segment placed via `compose_audio_timeline`
# below).


async def normalize_loudness(video_path: str, output_path: str, *, target_lufs: float = -16.0) -> None:
    """EBU R128 loudness normalization (ffmpeg's loudnorm filter) — the
    real remaining piece of B22/B25 that's actually small: run this as the
    last step before upload so a video with voiceover+music+ambient
    doesn't end up quieter or louder than platforms expect. -16 LUFS is a
    reasonable default for social platforms (YouTube/Instagram/TikTok all
    target somewhere in the -14 to -16 range; not vendor-verified against
    each platform's current spec)."""
    def _run() -> None:
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-i", video_path,
             "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
             "-movflags", "+faststart", output_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

    await asyncio.to_thread(_run)


async def trim_and_reframe_clip(
    source_path: str, output_path: str, *, start_seconds: float, end_seconds: float,
    target_aspect_ratio: str = "9:16",
) -> None:
    """Cuts [start_seconds, end_seconds) out of `source_path` and center-
    crops it to `target_aspect_ratio` (e.g. "9:16" for Shorts/Reels/TikTok
    from 16:9 source footage). Used by the Shorts/Repurpose workflows
    (workflows/shorts.py) — fundamentally different from every other
    function in this file: those all combine/generate media, this
    *selects and reframes* from existing footage, which is why the
    Shorts/Repurpose pipeline doesn't go through the AI Director/executor
    at all (see workflows/shorts.py's module docstring)."""
    width_ratio, height_ratio = (int(x) for x in target_aspect_ratio.split(":"))

    def _run() -> None:
        # crop=ih*W/H:ih (crop width to match target aspect at the source's
        # full height), then center it — the standard center-crop reframe.
        # Falls back visually poorly for extreme aspect changes (e.g. very
        # wide source concepts losing side content) — a real "smart crop"
        # that tracks the subject is a further improvement, not built here.
        vf = f"crop=ih*{width_ratio}/{height_ratio}:ih,scale=1080:1920" if width_ratio < height_ratio else f"crop=iw:iw*{height_ratio}/{width_ratio}"
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-ss", str(start_seconds), "-to", str(end_seconds), "-i", source_path,
             "-vf", vf, "-c:v", "libx264", "-c:a", "aac", output_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

    await asyncio.to_thread(_run)


async def reframe_video(source_path: str, output_path: str, *, target_aspect_ratio: str) -> None:
    """gap-closure: Content Factory / Export MVP (services/export/service.py).

    Same center-crop reframe math as `trim_and_reframe_clip` above, minus
    the trim — this reframes a WHOLE finished video (a Project's master)
    to a new aspect ratio, which is the mechanical part of turning one
    master into platform-specific variants (16:9 -> 9:16 for Shorts/TikTok,
    -> 1:1 or 4:5 for feed ads). Same center-crop limitation applies: no
    subject tracking, so an off-center subject in the source can end up
    poorly framed after an aggressive aspect change."""
    width_ratio, height_ratio = (int(x) for x in target_aspect_ratio.split(":"))

    def _run() -> None:
        if width_ratio == height_ratio:
            vf = f"crop=min(iw\\,ih):min(iw\\,ih)"
        elif width_ratio < height_ratio:
            vf = f"crop=ih*{width_ratio}/{height_ratio}:ih,scale=1080:1920"
        else:
            vf = f"crop=iw:iw*{height_ratio}/{width_ratio},scale=1920:1080"
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-i", source_path,
             "-vf", vf, "-c:v", "libx264", "-c:a", "aac", output_path],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

    await asyncio.to_thread(_run)


async def add_text_overlay(
    video_path: str, output_path: str, *, text: str, video_duration_seconds: float,
    show_for_seconds: float, position: str = "bottom_center", start_seconds: float | None = None,
) -> None:
    """gap-closure: BrandKit.cta_text was stored but never rendered
    anywhere in the render path — this burns it in as a simple text card
    over the last `show_for_seconds` of the video via ffmpeg's drawtext
    filter. `video_duration_seconds` must be probed by the caller
    (services/media/ffmpeg.py::probe_duration_seconds) beforehand — the
    drawtext filter's `enable` expression only has access to the current
    frame's own timestamp (`t`), not the whole stream's total duration, so
    the "last N seconds" window has to be computed as an absolute
    start-time here rather than relative to an in-filter `duration` value.
    Deliberately simple (no animation/fade) to match this project's
    existing overlay primitives."""
    positions = {
        "bottom_center": "x=(w-text_w)/2:y=h-text_h-60",
        "top_center": "x=(w-text_w)/2:y=60",
        "center": "x=(w-text_w)/2:y=(h-text_h)/2",
    }
    xy = positions.get(position, positions["bottom_center"])
    escaped_text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    start_at = max(0.0, video_duration_seconds - show_for_seconds) if start_seconds is None else max(0.0, float(start_seconds))
    end_at = video_duration_seconds if start_seconds is None else start_at + max(0.05, float(show_for_seconds))

    def _run() -> None:
        enable = f"gte(t\\,{start_at})" if start_seconds is None else f"between(t\\,{start_at}\\,{end_at})"
        drawtext = (
            f"drawtext=text='{escaped_text}':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.55:boxborderw=16:"
            f"{xy}:enable='{enable}'"
        )
        result = subprocess.run(
            [settings.ffmpeg_bin, "-y", "-i", video_path, "-vf", drawtext, "-c:a", "copy", output_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:800])

    await asyncio.to_thread(_run)


async def compose_audio_timeline(
    video_path: str, output_path: str, *,
    voice_segments: list[tuple[str, float]] | None = None,
    music_path: str | None = None,
    audio_segments: list[dict] | None = None,
    preserve_source_audio: bool = True,
) -> None:
    """Mix narration, music, ambience and source audio against the video timeline.

    ``audio_segments`` accepts dictionaries with ``path``, ``role``,
    ``start_seconds``, optional ``duration_seconds``, ``volume``, ``fade_in`` /
    ``fade_out`` and ``loop``. The legacy ``voice_segments``/``music_path``
    arguments remain supported for older callers and tests. Every track is
    trimmed or looped to its planned timeline span, delayed to its start, mixed
    at 48 kHz stereo, and finally padded/trimmed to the exact video duration.
    """
    video_duration = await probe_duration_seconds(video_path)
    source_has_audio = await probe_has_audio_stream(video_path) if preserve_source_audio else False
    tracks = list(audio_segments or [])
    tracks.extend({"path": path, "role": "narration", "start_seconds": start, "volume": 1.0} for path, start in (voice_segments or []))
    if music_path:
        tracks.append({"path": music_path, "role": "music", "start_seconds": 0.0, "volume": 0.22, "loop": True, "fade_in": 1.0, "fade_out": 2.0})
    tracks = [t for t in tracks if t.get("path") and float(t.get("start_seconds", 0.0)) < video_duration and float(t.get("volume", 1.0)) > 0]

    def _run() -> None:
        inputs: list[str] = ["-i", video_path]
        filter_parts: list[str] = []
        narration_labels: list[str] = []
        bed_labels: list[str] = []
        idx = 1
        for track_no, track in enumerate(tracks):
            path = str(track["path"])
            role = str(track.get("role", "music")).lower()
            start_seconds = max(0.0, float(track.get("start_seconds", 0.0)))
            timeline_remaining = max(0.05, video_duration - start_seconds)
            requested_duration = track.get("duration_seconds")
            duration = min(timeline_remaining, max(0.05, float(requested_duration))) if requested_duration is not None else timeline_remaining
            loop = bool(track.get("loop", False))
            if loop:
                inputs += ["-stream_loop", "-1"]
            inputs += ["-i", path]
            delay_ms = round(start_seconds * 1000)
            volume = max(0.0, min(float(track.get("volume", 1.0)), 4.0))
            fade_in = min(max(0.0, float(track.get("fade_in_seconds", track.get("fade_in", 0.0))),), duration)
            fade_out = min(max(0.0, float(track.get("fade_out_seconds", track.get("fade_out", 0.0))),), duration)
            label = f"aud{track_no}"
            chain = ["aresample=48000", "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo", "asetpts=PTS-STARTPTS", f"atrim=duration={duration:.3f}", f"volume={volume:.4f}"]
            if fade_in > 0.001:
                chain.append(f"afade=t=in:st=0:d={fade_in:.3f}")
            if fade_out > 0.001:
                chain.append(f"afade=t=out:st={max(0.0, duration-fade_out):.3f}:d={fade_out:.3f}")
            chain.append(f"adelay={delay_ms}|{delay_ms}")
            filter_parts.append(f"[{idx}:a]{','.join(chain)}[{label}]")
            if role in {"narration", "voiceover", "voice"}:
                narration_labels.append(f"[{label}]")
            else:
                bed_labels.append(f"[{label}]")
            idx += 1

        if source_has_audio:
            filter_parts.append("[0:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=0.35[source_audio]")
            bed_labels.append("[source_audio]")

        if len(narration_labels) == 1:
            filter_parts.append(f"{narration_labels[0]}anull[narration_mix]")
        elif len(narration_labels) > 1:
            filter_parts.append("".join(narration_labels) + f"amix=inputs={len(narration_labels)}:duration=longest:dropout_transition=0:normalize=0[narration_mix]")

        if len(bed_labels) == 1:
            filter_parts.append(f"{bed_labels[0]}anull[bed_mix]")
        elif len(bed_labels) > 1:
            filter_parts.append("".join(bed_labels) + f"amix=inputs={len(bed_labels)}:duration=longest:dropout_transition=0:normalize=0[bed_mix]")

        if narration_labels and bed_labels:
            filter_parts.append("[narration_mix]asplit=2[narration_main][narration_side]")
            filter_parts.append("[bed_mix][narration_side]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[bed_ducked]")
            filter_parts.append("[narration_main][bed_ducked]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[a_mix]")
        elif narration_labels:
            filter_parts.append("[narration_mix]anull[a_mix]")
        elif bed_labels:
            filter_parts.append("[bed_mix]anull[a_mix]")
        else:
            filter_parts.append("anullsrc=channel_layout=stereo:sample_rate=48000[a_mix]")

        filter_parts.append(f"[a_mix]apad=whole_dur={video_duration:.3f},atrim=duration={video_duration:.3f}[aout]")
        cmd = [settings.ffmpeg_bin, "-y", *inputs, "-filter_complex", ";".join(filter_parts),
               "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-ar", "48000", "-ac", "2", "-t", f"{video_duration:.3f}", "-movflags", "+faststart", output_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=settings.movie_assembly_max_seconds)
        if result.returncode != 0:
            raise FfmpegError(result.stderr[:1200])

    await asyncio.to_thread(_run)
