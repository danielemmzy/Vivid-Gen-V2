"""Turns a RenderManifest into a finished file — the single canonical
render path (see jobs/production.py::run_render_task, which assembles
the manifest via orchestration/render_manifest_builder.py's
`assemble_manifest_from_tasks` and calls this).

Sequence: concat video tracks in order -> compose the audio timeline
(per-scene voiceover segments at their real offsets, ducked music — see
services/media/ffmpeg.py::compose_audio_timeline) -> burn captions ->
apply image overlays -> burn CTA text -> upload. Every step is optional
except the video concat itself.
"""
import tempfile
from pathlib import Path

from app.core.logging import get_logger
from app.orchestration.render_manifest import RenderManifest
from app.services.media.ffmpeg import (
    add_text_overlay,
    burn_captions,
    compose_audio_timeline,
    concat_clips,
    normalize_clip_for_assembly,
    normalize_loudness,
    overlay_image,
    probe_duration_seconds,
    probe_has_audio_stream,
    trim_video_to_duration,
)
from app.services.storage.s3 import download_to_path, upload_from_path

logger = get_logger(__name__)


async def render(manifest: RenderManifest) -> str:
    """Returns the final output's S3 key. Raises FfmpegError (from
    services/media/ffmpeg.py) on any step's failure — the caller is
    responsible for marking the project/render job FAILED with that
    message, matching how `run_render_task` handles its own failures."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        video_paths = []
        for track in sorted(manifest.video_tracks, key=lambda t: t.order):
            source_path = str(tmp / f"video_{track.order}_{track.asset_id}_source.mp4")
            normalized_path = str(tmp / f"video_{track.order}_{track.asset_id}_normalized.mp4")
            download_to_path(track.s3_key, source_path)
            desired_duration = track.duration_seconds
            if desired_duration is None:
                desired_duration = await probe_duration_seconds(source_path)
            await normalize_clip_for_assembly(
                source_path, normalized_path, width=manifest.output_width, height=manifest.output_height,
                frame_rate=manifest.frame_rate, duration_seconds=desired_duration,
                source_start_seconds=track.source_start_seconds, source_volume=track.source_volume, source_muted=track.source_muted,
            )
            video_paths.append(normalized_path)

        current = str(tmp / "stage_0_concat.mp4")
        await concat_clips(video_paths, current)

        # Compose every requested timeline track at its own in-point. Legacy
        # whole-file voiceover tracks and the previous voice_segments schema
        # remain readable so existing production records still render.
        audio_segments: list[dict] = []
        for i, seg in enumerate(manifest.voice_segments):
            local_path = str(tmp / f"voiceseg_{i}_{seg.asset_id}.mp3")
            download_to_path(seg.s3_key, local_path)
            source_duration = await probe_duration_seconds(local_path)
            segment_duration = min(float(seg.duration_seconds), source_duration) if seg.duration_seconds is not None else source_duration
            audio_segments.append({
                "path": local_path, "role": "narration", "start_seconds": seg.start_seconds,
                "duration_seconds": segment_duration, "volume": seg.volume,
                "fade_in_seconds": seg.fade_in_seconds, "fade_out_seconds": seg.fade_out_seconds, "loop": False,
            })

        for i, track in enumerate(manifest.audio_tracks):
            local_path = str(tmp / f"audio_{i}_{track.role}_{track.asset_id}.media")
            download_to_path(track.s3_key, local_path)
            source_duration = await probe_duration_seconds(local_path)
            role = "narration" if track.role in {"voiceover", "narration", "voice"} else track.role
            requested_duration = track.duration_seconds
            if requested_duration is None:
                requested_duration = max(0.05, (manifest.target_duration_seconds or await probe_duration_seconds(current)) - track.start_seconds)
            timeline_duration = float(requested_duration) if track.loop else min(float(requested_duration), source_duration)
            audio_segments.append({
                "path": local_path, "role": role, "start_seconds": track.start_seconds,
                "duration_seconds": timeline_duration, "volume": track.volume,
                "fade_in_seconds": track.fade_in_seconds, "fade_out_seconds": track.fade_out_seconds, "loop": track.loop,
            })

        if audio_segments:
            next_stage = str(tmp / "stage_audio.mp4")
            await compose_audio_timeline(current, next_stage, audio_segments=audio_segments, preserve_source_audio=True)
            current = next_stage
            next_stage = str(tmp / "stage_loudness.mp4")
            await normalize_loudness(current, next_stage)
            current = next_stage

        if manifest.caption_track:
            srt_local = str(tmp / f"captions_{manifest.caption_track.asset_id}.srt")
            download_to_path(manifest.caption_track.s3_key, srt_local)
            next_stage = str(tmp / "stage_captions.mp4")
            await burn_captions(
                current, srt_local, next_stage, style=manifest.caption_track.style,
                primary_color=manifest.caption_track.primary_color,
                outline_color=manifest.caption_track.outline_color,
                font_family=manifest.caption_track.font_family,
            )
            current = next_stage

        for i, overlay in enumerate(manifest.overlays):
            overlay_local = str(tmp / f"overlay_{i}_{overlay.asset_id}.png")
            download_to_path(overlay.s3_key, overlay_local)
            next_stage = str(tmp / f"stage_overlay_{i}.mp4")
            await overlay_image(current, overlay_local, next_stage, position=overlay.position, opacity=overlay.opacity)
            current = next_stage

        # gap-closure: BrandKit.cta_text was previously stored and never
        # rendered — burned in here, last, so it sits on top of captions/
        # logo rather than under them.
        for i, text_overlay in enumerate(manifest.text_overlays):
            video_duration = await probe_duration_seconds(current)
            next_stage = str(tmp / f"stage_text_{i}.mp4")
            await add_text_overlay(
                current, next_stage, text=text_overlay.text, video_duration_seconds=video_duration,
                show_for_seconds=text_overlay.duration_seconds, position=text_overlay.position,
                start_seconds=text_overlay.start_seconds,
            )
            current = next_stage

        actual_duration = await probe_duration_seconds(current)
        if not await probe_has_audio_stream(current):
            from app.services.media.ffmpeg import FfmpegError
            raise FfmpegError("Final export has no audio stream; the output was not published.")
        if manifest.target_duration_seconds is not None:
            target_duration = float(manifest.target_duration_seconds)
            # AAC frame padding can add ~21ms per concatenated clip. Trim that
            # accumulated container overrun once at the final stage, rather
            # than allowing long movies to drift by seconds after many clips.
            if actual_duration > target_duration + 0.02:
                exact_path = str(tmp / "stage_final_duration.mp4")
                await trim_video_to_duration(current, exact_path, duration_seconds=target_duration)
                current = exact_path
                actual_duration = await probe_duration_seconds(current)
            if abs(actual_duration - target_duration) > 0.75:
                from app.services.media.ffmpeg import FfmpegError
                raise FfmpegError(
                    f"Final duration validation failed: expected {target_duration:.2f}s, "
                    f"rendered {actual_duration:.2f}s. The output was not published."
                )
        upload_from_path(current, manifest.output_s3_key, "video/mp4")
        logger.info(
            "render_manifest_completed", project_id=manifest.project_id,
            video_tracks=len(manifest.video_tracks), voice_segments=len(manifest.voice_segments),
            audio_tracks=len(manifest.audio_tracks), has_captions=manifest.caption_track is not None,
            overlays=len(manifest.overlays), text_overlays=len(manifest.text_overlays),
        )
        return manifest.output_s3_key
