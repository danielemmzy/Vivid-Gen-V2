"""gap-closure (0007): render-domain logic, now split into per-task
pieces called by jobs/production.py's job functions instead of one
monolithic `build_render_manifest` that resolved everything inline in a
single ARQ job.

Round 2 built `build_render_manifest` as one function doing scene-offset
computation, voice synthesis, caption transcription, music/branding
resolution, and manifest assembly, all in one call from
`jobs/media.py::assemble_movie`. That is exactly the "flat" execution
this round replaces: VOICE, CAPTIONS, MUSIC, and BRANDING are now
independent DAG tasks (orchestration/dag.py) with their own ARQ jobs,
each storing its result in `ProductionTask.output_json`; RENDER reads
those results to assemble the final `RenderManifest` rather than
re-resolving anything. The actual resolution logic (TTS synthesis,
transcription+shift+merge, asset dedup) is UNCHANGED from round 2 — only
how it's split across tasks is new.
"""
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import ProductionTaskStatus, ProductionTaskType
from app.core.logging import get_logger
from app.models.asset import Asset
from app.models.brand_kit import BrandKit
from app.models.generation import Generation
from app.models.production import Production
from app.models.project import Project
from app.models.production_task import ProductionTask
from app.orchestration import dag
from app.orchestration.production_plan import ProductionPlan
from app.orchestration.render_manifest import AudioTrack, CaptionTrack, ImageOverlay, RenderManifest, TextOverlay, VideoTrack, VoiceSegment
from app.repository.brand_kits import BrandKitRepository
from app.services.media.captions import write_srt
from app.services.media.ffmpeg import normalize_audio_file
from app.services.providers.audio.registry import get_transcription_provider, get_tts_provider
from app.services.storage.s3 import download_to_path, presign_download, upload_from_path

logger = get_logger(__name__)


async def _get_or_create_asset(
    session: AsyncSession, *, project_id: str, user_id: str, type_: str, source: str,
    s3_key: str, source_generation_id: str | None = None, duration_seconds: float | None = None,
) -> Asset:
    """Idempotent by (project_id, s3_key) — a re-render of the same
    project must not pile up duplicate Asset rows for the same
    voiceover/music/caption file every time."""
    existing = (
        await session.execute(select(Asset).where(Asset.project_id == project_id, Asset.s3_key == s3_key))
    ).scalar_one_or_none()
    if existing:
        return existing
    asset = Asset(
        id="asset_" + uuid4().hex, project_id=project_id, user_id=user_id, type=type_, source=source,
        s3_key=s3_key, duration_seconds=duration_seconds, source_generation_id=source_generation_id,
    )
    session.add(asset)
    await session.flush()
    return asset


async def load_plan_and_brand_kit(session: AsyncSession, production: Production) -> tuple[ProductionPlan, BrandKit | None]:
    from app.orchestration.executor import load_plan_record

    plan_record = await load_plan_record(session, production.id)
    plan = ProductionPlan.model_validate(plan_record.plan_json)
    brand_kit = None
    if plan.branding.enabled and plan.branding.brand_kit_id:
        brand_kit = await BrandKitRepository(session).get_owned(plan.branding.brand_kit_id, production.user_id)
        if not brand_kit:
            logger.warning("brand_kit_not_found", production_id=production.id, brand_kit_id=plan.branding.brand_kit_id)
    return plan, brand_kit


async def get_scene_tasks_ordered(session: AsyncSession, production_id: str) -> list[ProductionTask]:
    tasks = await dag.list_tasks_for_production(session, production_id)
    scene_tasks = [t for t in tasks if t.type == ProductionTaskType.SCENE]
    return sorted(scene_tasks, key=lambda t: t.scene_number or 0)


async def compute_scene_offsets_and_tracks(session: AsyncSession, production_id: str) -> tuple[dict[int, float], list[VideoTrack]]:
    """Build ordered video tracks from generated shots, honoring the saved
    editor timeline when present. Scene offsets are recomputed from the final
    clip order so voiceover/caption timing follows reorder and trims."""
    scene_tasks = await get_scene_tasks_ordered(session, production_id)
    production = await session.get(Production, production_id)
    project = await session.get(Project, production.project_id) if production else None
    editor_timeline = (project.metadata_json or {}).get("editor_timeline") if project else None
    editor_clips = editor_timeline.get("clips") if isinstance(editor_timeline, dict) else None
    base_by_shot: dict[str, VideoTrack] = {}
    cumulative_default = 0.0
    offsets_default: dict[int, float] = {}
    order = 10
    for task in scene_tasks:
        if task.status != ProductionTaskStatus.COMPLETED or not task.shot_id:
            continue
        from app.models.project import Shot
        shot = await session.get(Shot, task.shot_id)
        if not shot or not shot.generation_id:
            continue
        generation = await session.get(Generation, shot.generation_id)
        if not generation or not generation.output_s3_key:
            continue
        source_duration = float(generation.duration_seconds) if generation.duration_seconds else float(shot.duration_seconds)
        clip_duration = min(source_duration, float(shot.timeline_duration_seconds)) if shot.timeline_duration_seconds else source_duration
        clip_asset = await _get_or_create_asset(
            session, project_id=shot.project_id, user_id=generation.user_id, type_="video", source="generation",
            s3_key=generation.output_s3_key, source_generation_id=generation.id, duration_seconds=source_duration,
        )
        base_by_shot[shot.id] = VideoTrack(
            asset_id=clip_asset.id, s3_key=clip_asset.s3_key, order=order, duration_seconds=source_duration,
            scene_number=task.scene_number,
        )
        if task.scene_number is not None:
            offsets_default.setdefault(task.scene_number, cumulative_default)
        cumulative_default += clip_duration
        order += 10

    # No editor timeline means preserve the legacy storyboard order and shot-level trim.
    if not isinstance(editor_clips, list):
        legacy_tracks = []
        cumulative = 0.0
        offsets: dict[int, float] = {}
        for task in scene_tasks:
            if not task.shot_id or task.shot_id not in base_by_shot:
                continue
            base = base_by_shot[task.shot_id]
            from app.models.project import Shot
            shot = await session.get(Shot, task.shot_id)
            source_duration = float(base.duration_seconds or 0.0)
            clip_duration = min(source_duration, float(shot.timeline_duration_seconds)) if shot and shot.timeline_duration_seconds else source_duration
            legacy_tracks.append(base.model_copy(update={"order": 10 + len(legacy_tracks) * 10, "duration_seconds": clip_duration}))
            if base.scene_number is not None:
                offsets.setdefault(base.scene_number, cumulative)
            cumulative += clip_duration
        return offsets, legacy_tracks

    offsets: dict[int, float] = {}
    tracks: list[VideoTrack] = []
    cumulative = 0.0
    for clip in editor_clips:
        if not isinstance(clip, dict):
            continue
        shot_id = clip.get("shotId")
        base = base_by_shot.get(shot_id) if isinstance(shot_id, str) else None
        if not base:
            continue
        source_duration = float(clip.get("duration") or base.duration_seconds or 0.0)
        trim_start = max(0.0, float(clip.get("trimStart", 0.0) or 0.0))
        trim_end = max(0.0, float(clip.get("trimEnd", 0.0) or 0.0))
        usable_duration = source_duration - trim_start - trim_end
        if usable_duration <= 0.05:
            continue
        track = base.model_copy(update={
            "order": 10 + len(tracks) * 10, "duration_seconds": usable_duration,
            "source_start_seconds": trim_start, "source_volume": max(0.0, min(4.0, float(clip.get("volume", 100) or 0) / 100.0)),
            "source_muted": bool(clip.get("muted", False)),
        })
        tracks.append(track)
        if track.scene_number is not None:
            offsets.setdefault(track.scene_number, cumulative)
        cumulative += usable_duration
    return offsets, tracks


async def synthesize_voice_segments(
    session: AsyncSession, production: Production, plan: ProductionPlan, brand_kit: BrandKit | None, tmpdir: str,
) -> dict:
    """Called by jobs/production.py::run_voice_task. Returns an
    output_json-shaped dict: {"segments": [{"asset_id","s3_key",
    "start_seconds"}]}. Unchanged synthesis logic from round 2 — each
    scene's line is its own Asset with its own real timeline offset
    (from `compute_scene_offsets_and_tracks`), rather than one
    concatenated file mixed over the whole video."""
    if not plan.voiceover.enabled:
        return {"segments": []}
    scene_offsets, _tracks = await compute_scene_offsets_and_tracks(session, production.id)
    lines = [
        (s.scene_number, s.voiceover_line)
        for s in sorted(plan.scenes, key=lambda s: s.scene_number)
        if s.voiceover_line and s.scene_number in scene_offsets
    ]
    if not lines:
        raise RuntimeError("Narration is enabled but the approved plan contains no scene narration lines")

    voice_id = plan.voiceover.voice_id or (brand_kit.voice_id if brand_kit else None)
    reference_audio_url = None
    if plan.voiceover.reference_audio_s3_key:
        # Plan validator restricts this key to the authenticated user's voice-reference prefix.
        reference_audio_url = presign_download(plan.voiceover.reference_audio_s3_key)
    provider = get_tts_provider(plan.voiceover.provider)
    segments = []
    failures: list[str] = []
    # Bounded fan-out reduces long-form narration latency without unbounded
    # provider requests. Asset/S3/database writes remain sequential on the
    # single AsyncSession to avoid concurrent session use.
    import asyncio
    semaphore = asyncio.Semaphore(settings.audio_tts_max_concurrency)

    async def synthesize_one(scene_number: int, line: str) -> tuple[int, str, str, float | None, str | None]:
        provider_path = str(Path(tmpdir) / f"voiceover_{scene_number}.provider")
        clip_path = str(Path(tmpdir) / f"voiceover_{scene_number}.mp3")
        try:
            async with semaphore:
                await provider.synthesize(
                    text=line, voice_id=voice_id, style=plan.voiceover.style, output_path=provider_path,
                    reference_audio_url=reference_audio_url,
                )
                duration = await normalize_audio_file(provider_path, clip_path)
            return scene_number, clip_path, provider_path, duration, None
        except Exception as exc:  # noqa: BLE001 - selected narration must not silently disappear
            logger.warning("voiceover_line_failed", production_id=production.id, scene_number=scene_number, cause=str(exc))
            return scene_number, clip_path, provider_path, None, str(exc)[:180]

    synthesized = await asyncio.gather(*(synthesize_one(scene_number, line) for scene_number, line in lines))
    for scene_number, clip_path, _provider_path, duration, error in synthesized:
        if error is not None or duration is None:
            failures.append(f"scene {scene_number}: {error or 'unknown synthesis error'}")
            continue
        output_key = f"{settings.s3_output_prefix}/{production.user_id}/productions/{production.id}/voiceover_scene{scene_number}_{uuid4().hex[:8]}.mp3"
        upload_from_path(clip_path, output_key, "audio/mpeg")
        asset = await _get_or_create_asset(session, project_id=production.project_id, user_id=production.user_id, type_="voiceover", source="tts", s3_key=output_key, duration_seconds=duration)
        segments.append({"asset_id": asset.id, "s3_key": asset.s3_key, "scene_number": scene_number, "start_seconds": scene_offsets[scene_number], "duration_seconds": duration, "volume": plan.voiceover.volume})
    if failures:
        raise RuntimeError("Narration generation failed for " + "; ".join(failures))
    return {"segments": segments}


async def transcribe_captions(session: AsyncSession, production: Production, voice_output: dict, tmpdir: str) -> dict | None:
    """Called by jobs/production.py::run_captions_task with VOICE's
    output_json. Transcribes each scene's voiceover clip separately and
    shifts timestamps by that scene's real start offset, merging into
    one combined .srt — unchanged from round 2."""
    segments = voice_output.get("segments") or []
    if not segments:
        return None

    provider = get_transcription_provider()
    all_segments: list[dict] = []
    for seg in segments:
        try:
            local_audio = str(Path(tmpdir) / f"caption_source_{seg['asset_id']}.mp3")
            download_to_path(seg["s3_key"], local_audio)
            transcribed = await provider.transcribe(audio_path=local_audio)
        except Exception as exc:  # noqa: BLE001 - captions are optional polish, never fail the whole render over them
            logger.warning("caption_transcription_failed", production_id=production.id, asset_id=seg["asset_id"], cause=str(exc))
            continue
        for t in transcribed:
            all_segments.append({"start": t["start"] + seg["start_seconds"], "end": t["end"] + seg["start_seconds"], "text": t["text"]})

    if not all_segments:
        return None
    all_segments.sort(key=lambda s: s["start"])

    srt_local = str(Path(tmpdir) / "captions.srt")
    write_srt(all_segments, srt_local)
    output_key = f"{settings.s3_output_prefix}/{production.user_id}/productions/{production.id}/captions_{uuid4().hex[:8]}.srt"
    upload_from_path(srt_local, output_key, "text/plain")
    asset = await _get_or_create_asset(session, project_id=production.project_id, user_id=production.user_id, type_="captions", source="render", s3_key=output_key)
    return {"asset_id": asset.id, "s3_key": asset.s3_key}


async def resolve_music(
    session: AsyncSession, production: Production, plan: ProductionPlan,
    brand_kit: BrandKit | None, tmpdir: str,
) -> dict:
    """Resolve or generate every optional music/ambience timeline track.

    Brand-kit music is preserved as the preferred source when present. If the
    user enabled music without a brand-kit track, a configured prompt-to-audio
    provider generates a bed. Ambience uses the same provider-neutral contract
    but its own prompt/duration profile. Missing provider configuration raises
    an error instead of silently publishing a movie without requested audio.
    """
    tracks: list[dict] = []
    target_duration = float(plan.duration_seconds)

    if plan.music.enabled:
        start = min(float(plan.music.start_seconds), max(0.0, target_duration - 0.05))
        span = min(float(plan.music.duration_seconds or max(1, int(target_duration - start))), max(0.05, target_duration - start))
        if brand_kit and brand_kit.default_music_s3_key:
            asset = await _get_or_create_asset(
                session, project_id=production.project_id, user_id=production.user_id, type_="music", source="upload",
                s3_key=brand_kit.default_music_s3_key,
            )
        else:
            from app.services.providers.audio.generation_registry import get_audio_generation_provider
            provider = get_audio_generation_provider(plan.music.provider)
            generated_path = str(Path(tmpdir) / "generated_music.provider")
            normalized_path = str(Path(tmpdir) / "generated_music.mp3")
            prompt_parts = ["Instrumental background music for a finished video", plan.music.mood, plan.music.genre, "no intelligible speech or lyrics"]
            await provider.generate(prompt=", ".join(part.strip() for part in prompt_parts if part and part.strip()), duration_seconds=max(1, min(180, round(span))), role="music", output_path=generated_path)
            measured_duration = await normalize_audio_file(generated_path, normalized_path)
            output_key = f"{settings.s3_output_prefix}/{production.user_id}/productions/{production.id}/music_{uuid4().hex[:8]}.mp3"
            upload_from_path(normalized_path, output_key, "audio/mpeg")
            asset = await _get_or_create_asset(session, project_id=production.project_id, user_id=production.user_id, type_="music", source="audio_generation", s3_key=output_key, duration_seconds=measured_duration)
        tracks.append({
            "asset_id": asset.id, "s3_key": asset.s3_key, "role": "music", "start_seconds": start,
            "duration_seconds": span, "volume": plan.music.volume, "fade_in_seconds": plan.music.fade_in_seconds,
            "fade_out_seconds": plan.music.fade_out_seconds, "loop": plan.music.loop,
        })

    if plan.ambience.enabled:
        start = min(float(plan.ambience.start_seconds), max(0.0, target_duration - 0.05))
        span = min(float(plan.ambience.duration_seconds or max(1, int(target_duration - start))), max(0.05, target_duration - start))
        from app.services.providers.audio.generation_registry import get_audio_generation_provider
        provider = get_audio_generation_provider(plan.ambience.provider)
        generated_path = str(Path(tmpdir) / "generated_ambience.provider")
        normalized_path = str(Path(tmpdir) / "generated_ambience.mp3")
        ambience_prompt = plan.ambience.prompt or "Natural cinematic environmental ambience matching the visual scene; no music, no speech"
        measured_duration = await provider.generate(
            prompt=ambience_prompt, duration_seconds=max(1, min(30, round(span))), role="ambience", output_path=generated_path,
        )
        normalized_duration = await normalize_audio_file(generated_path, normalized_path)
        output_key = f"{settings.s3_output_prefix}/{production.user_id}/productions/{production.id}/ambience_{uuid4().hex[:8]}.mp3"
        upload_from_path(normalized_path, output_key, "audio/mpeg")
        asset = await _get_or_create_asset(session, project_id=production.project_id, user_id=production.user_id, type_="ambience", source="audio_generation", s3_key=output_key, duration_seconds=normalized_duration or measured_duration)
        tracks.append({
            "asset_id": asset.id, "s3_key": asset.s3_key, "role": "ambience", "start_seconds": start,
            "duration_seconds": span, "volume": plan.ambience.volume, "fade_in_seconds": plan.ambience.fade_in_seconds,
            "fade_out_seconds": plan.ambience.fade_out_seconds, "loop": plan.ambience.loop,
        })

    return {"tracks": tracks}


async def resolve_branding(session: AsyncSession, production: Production, brand_kit: BrandKit | None) -> dict | None:
    """Called by jobs/production.py::run_branding_task. Resolves every
    BrandKit reference the render path applies (logo, watermark, intro/
    outro clip, CTA text) into one output_json dict RENDER reads
    directly — same fields round 2's monolithic builder resolved inline."""
    if not brand_kit:
        return None
    result: dict = {}
    if brand_kit.logo_s3_key:
        logo_asset = await _get_or_create_asset(session, project_id=production.project_id, user_id=production.user_id, type_="logo", source="upload", s3_key=brand_kit.logo_s3_key)
        result["logo"] = {"asset_id": logo_asset.id, "s3_key": logo_asset.s3_key}
    if brand_kit.watermark_s3_key:
        watermark_asset = await _get_or_create_asset(session, project_id=production.project_id, user_id=production.user_id, type_="logo", source="upload", s3_key=brand_kit.watermark_s3_key)
        result["watermark"] = {"asset_id": watermark_asset.id, "s3_key": watermark_asset.s3_key}
    if brand_kit.intro_asset_id:
        intro_asset = await session.get(Asset, brand_kit.intro_asset_id)
        if intro_asset and intro_asset.user_id == production.user_id:
            result["intro"] = {"asset_id": intro_asset.id, "s3_key": intro_asset.s3_key, "duration_seconds": float(intro_asset.duration_seconds or 0.0)}
        else:
            logger.warning("brand_kit_intro_asset_missing", production_id=production.id, asset_id=brand_kit.intro_asset_id)
    if brand_kit.outro_asset_id:
        outro_asset = await session.get(Asset, brand_kit.outro_asset_id)
        if outro_asset and outro_asset.user_id == production.user_id:
            result["outro"] = {"asset_id": outro_asset.id, "s3_key": outro_asset.s3_key}
        else:
            logger.warning("brand_kit_outro_asset_missing", production_id=production.id, asset_id=brand_kit.outro_asset_id)
    if brand_kit.cta_text:
        result["cta_text"] = brand_kit.cta_text
    # Caption color/font overrides applied only when the plan left
    # captions.style at its default — see assemble_manifest_from_tasks.
    result["primary_color"] = brand_kit.primary_color
    result["secondary_color"] = brand_kit.secondary_color
    result["font_family"] = brand_kit.font_family
    return result or None


async def assemble_manifest_from_tasks(session: AsyncSession, production: Production, plan: ProductionPlan) -> RenderManifest:
    """Called by jobs/production.py::run_render_task once every
    dependency (all SCENE tasks + VOICE + CAPTIONS + MUSIC + BRANDING)
    is satisfied. Reads their `output_json` directly — no re-resolution,
    matching the round-3 requirement that RENDER consume its
    dependencies' actual outputs rather than just running after them
    incidentally."""
    scene_offsets, video_tracks = await compute_scene_offsets_and_tracks(session, production.id)
    project = await session.get(Project, production.project_id)
    editor_timeline = (project.metadata_json or {}).get("editor_timeline") if project else None
    has_editor_timeline = isinstance(editor_timeline, dict) and isinstance(editor_timeline.get("clips"), list)
    resolution = project.resolution if project and project.resolution in ("420p", "720p") else "720p"
    timeline_aspect = editor_timeline.get("aspectRatio") if has_editor_timeline else None
    aspect_ratio = timeline_aspect if timeline_aspect in ("16:9", "9:16", "1:1", "4:3", "3:4", "4:5") else (project.aspect_ratio if project and project.aspect_ratio in ("16:9", "9:16", "1:1", "4:3", "3:4") else "16:9")
    short_edge = 420 if resolution == "420p" else 720
    ratio_w, ratio_h = (int(part) for part in aspect_ratio.split(":"))
    if ratio_w >= ratio_h:
        output_height = short_edge
        output_width = max(2, round((short_edge * ratio_w / ratio_h) / 2) * 2)
    else:
        output_width = short_edge
        output_height = max(2, round((short_edge * ratio_h / ratio_w) / 2) * 2)

    # The plan duration is a final timeline target. When an intro/outro is
    # present, the current branding contract intentionally extends the movie,
    # so strict target validation is disabled for that render.
    editor_duration = sum(float(track.duration_seconds or 0.0) for track in video_tracks)
    manifest = RenderManifest(
        project_id=production.project_id, video_tracks=video_tracks,
        output_width=output_width, output_height=output_height, frame_rate=24,
        target_duration_seconds=editor_duration if has_editor_timeline else float(plan.duration_seconds),
        output_s3_key=f"{settings.s3_output_prefix}/{production.user_id}/projects/{production.project_id}/master.mp4",
    )

    branding_task = await dag.get_task_by_type(session, production.id, ProductionTaskType.BRANDING)
    branding = branding_task.output_json if branding_task and branding_task.status == ProductionTaskStatus.COMPLETED else None

    intro_duration = 0.0
    if branding and branding.get("intro"):
        intro = branding["intro"]
        intro_duration = float(intro.get("duration_seconds") or 0.0)
        manifest.video_tracks.insert(0, VideoTrack(asset_id=intro["asset_id"], s3_key=intro["s3_key"], order=0, duration_seconds=intro_duration or None))
    if branding and branding.get("outro"):
        outro = branding["outro"]
        outro_duration = float(outro.get("duration_seconds") or 0.0)
        manifest.video_tracks.append(VideoTrack(asset_id=outro["asset_id"], s3_key=outro["s3_key"], order=100000, duration_seconds=outro_duration or None))
    if (branding and (branding.get("intro") or branding.get("outro"))):
        # Current branding semantics append these clips outside the scene
        # timeline; do not compare that intentionally extended export with
        # the scene-only target duration.
        manifest.target_duration_seconds = None

    voice_task = await dag.get_task_by_type(session, production.id, ProductionTaskType.VOICE)
    if voice_task and voice_task.status == ProductionTaskStatus.COMPLETED and voice_task.output_json:
        # Legacy voice task outputs lack scene_number. Their list order follows
        # the sorted narration lines, so use that stable ordering as a fallback.
        voice_scene_numbers = [scene.scene_number for scene in sorted(plan.scenes, key=lambda item: item.scene_number) if scene.voiceover_line]
        for index, seg in enumerate(voice_task.output_json.get("segments", [])):
            scene_number = seg.get("scene_number")
            if scene_number is None and index < len(voice_scene_numbers):
                scene_number = voice_scene_numbers[index]
            start_seconds = scene_offsets.get(scene_number, float(seg.get("start_seconds", 0.0)))
            manifest.voice_segments.append(VoiceSegment(
                asset_id=seg["asset_id"], s3_key=seg["s3_key"], start_seconds=start_seconds + intro_duration,
                duration_seconds=seg.get("duration_seconds"), volume=float(seg.get("volume", plan.voiceover.volume)),
            ))

    captions_task = await dag.get_task_by_type(session, production.id, ProductionTaskType.CAPTIONS)
    if captions_task and captions_task.status == ProductionTaskStatus.COMPLETED and captions_task.output_json:
        apply_brand_caption_colors = branding is not None and plan.captions.style == "minimal"
        manifest.caption_track = CaptionTrack(
            asset_id=captions_task.output_json["asset_id"], s3_key=captions_task.output_json["s3_key"], style=plan.captions.style,
            primary_color=branding.get("primary_color") if apply_brand_caption_colors else None,
            outline_color=branding.get("secondary_color") if apply_brand_caption_colors else None,
            font_family=branding.get("font_family") if apply_brand_caption_colors else None,
        )

    music_task = await dag.get_task_by_type(session, production.id, ProductionTaskType.MUSIC)
    if music_task and music_task.status == ProductionTaskStatus.COMPLETED and music_task.output_json:
        music_output = music_task.output_json
        # Backward compatibility with projects whose task output stored one
        # brand-kit music asset before the general audio timeline was added.
        if "tracks" in music_output:
            for track in music_output.get("tracks", []):
                manifest.audio_tracks.append(AudioTrack(
                    asset_id=track["asset_id"], s3_key=track["s3_key"], role=track.get("role", "music"),
                    start_seconds=float(track.get("start_seconds", 0.0)), duration_seconds=track.get("duration_seconds"),
                    volume=float(track.get("volume", 0.22)), fade_in_seconds=float(track.get("fade_in_seconds", 0.0)),
                    fade_out_seconds=float(track.get("fade_out_seconds", 0.0)), loop=bool(track.get("loop", True)),
                ))
        elif music_output.get("asset_id") and music_output.get("s3_key"):
            manifest.audio_tracks.append(AudioTrack(asset_id=music_output["asset_id"], s3_key=music_output["s3_key"], role="music", volume=0.22, fade_in_seconds=1.0, fade_out_seconds=2.0, loop=True))

    if branding:
        if branding.get("logo"):
            manifest.overlays.append(ImageOverlay(asset_id=branding["logo"]["asset_id"], s3_key=branding["logo"]["s3_key"], position="bottom_right", opacity=0.85))
        if branding.get("watermark"):
            manifest.overlays.append(ImageOverlay(asset_id=branding["watermark"]["asset_id"], s3_key=branding["watermark"]["s3_key"], position="top_left", opacity=0.5))
        if branding.get("cta_text"):
            manifest.text_overlays.append(TextOverlay(text=branding["cta_text"], duration_seconds=4.0, position="bottom_center"))

    if has_editor_timeline:
        for layer in editor_timeline.get("textLayers", []):
            if not isinstance(layer, dict):
                continue
            text = str(layer.get("text", ""))[:500].strip()
            if not text:
                continue
            style = layer.get("style")
            position = "center" if style == "title" else "top_center" if style == "label" else "bottom_center"
            start_seconds = max(0.0, float(layer.get("start", 0.0) or 0.0))
            duration_seconds = max(0.05, min(600.0, float(layer.get("duration", 3.0) or 3.0)))
            manifest.text_overlays.append(TextOverlay(
                text=text, duration_seconds=duration_seconds, position=position, start_seconds=start_seconds,
            ))

    logger.info(
        "render_manifest_assembled", production_id=production.id, video_tracks=len(manifest.video_tracks),
        voice_segments=len(manifest.voice_segments), has_captions=manifest.caption_track is not None,
        overlays=len(manifest.overlays), text_overlays=len(manifest.text_overlays),
    )
    return manifest
