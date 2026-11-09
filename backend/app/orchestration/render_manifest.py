"""V2 Phase 9: the RenderManifest (spec §62).

A plain description of what a render should contain — video tracks in
order, one optional audio overlay, one optional caption file, overlay
images — completely separate from *how* ffmpeg does it. Business logic
(the executor, workflow presets) builds one of these; only
`services/media/renderer.py` knows any ffmpeg-specific detail. This makes
"what will this render produce" testable without running ffmpeg at all —
you can assert on the manifest a workflow builds without a real video
file anywhere.
"""
from pydantic import BaseModel, Field


class VideoTrack(BaseModel):
    asset_id: str
    s3_key: str
    order: int
    # Desired usable timeline duration; None means use the full source clip.
    duration_seconds: float | None = None
    source_start_seconds: float = Field(default=0.0, ge=0.0)
    source_volume: float = Field(default=1.0, ge=0.0, le=4.0)
    source_muted: bool = False
    scene_number: int | None = None


class AudioTrack(BaseModel):
    asset_id: str
    s3_key: str
    role: str  # music | ambience | voiceover (legacy whole-file narration)
    start_seconds: float = Field(default=0.0, ge=0.0)
    duration_seconds: float | None = Field(default=None, gt=0.0)  # timeline span; may exceed source duration when loop=True
    volume: float = Field(default=1.0, ge=0.0, le=4.0)
    fade_in_seconds: float = Field(default=0.0, ge=0.0)
    fade_out_seconds: float = Field(default=0.0, ge=0.0)
    loop: bool = True
    # gap-closure (0006): `duck_existing` (a per-track ducking toggle) was
    # removed — under compose_audio_timeline, ducking is inherent to the
    # algorithm whenever both a voice mix and a music track are present,
    # not a per-track setting, so the field had no consumer left to read
    # it. Leaving it in place, unread, would have been exactly the kind
    # of "declared but not wired" gap this pass was meant to close.


class VoiceSegment(BaseModel):
    """gap-closure (0006): real per-scene audio timing (P0.8 in the
    audit). Previously every scene's voiceover line was concatenated into
    one undifferentiated file and mixed over the WHOLE video via a plain
    `AudioTrack` — if scene 3 was skipped or ran a different length than
    planned, every later scene's line would drift out of sync with its
    own visuals. Each segment now carries the exact offset (seconds from
    the start of the final concatenated video) it belongs at, computed in
    render_manifest_builder.py from the ACTUAL durations of the video
    tracks that precede it — not the Director's planned scene durations,
    which can differ from what a provider actually generated. See
    services/media/ffmpeg.py::compose_audio_timeline for how these are
    placed (ffmpeg `adelay`) and mixed with any music track (ducked under
    the voice via `sidechaincompress`, not just lowered for the whole
    video's duration)."""
    asset_id: str
    s3_key: str
    start_seconds: float = Field(ge=0.0)
    duration_seconds: float | None = Field(default=None, gt=0.0)
    volume: float = Field(default=1.0, ge=0.0, le=4.0)
    fade_in_seconds: float = Field(default=0.0, ge=0.0)
    fade_out_seconds: float = Field(default=0.0, ge=0.0)


class CaptionTrack(BaseModel):
    asset_id: str
    s3_key: str  # .srt
    style: str = "minimal"
    # gap-closure: previously BrandKit.primary_color/secondary_color/
    # font_family were stored but never read anywhere in the render path
    # (see build_render_manifest.py) — these let a brand kit override the
    # base `style` preset's colors/font without needing a 5th hardcoded
    # style preset per brand.
    primary_color: str | None = None    # e.g. "#FFFFFF" - overrides the style preset's caption text color
    outline_color: str | None = None    # e.g. "#000000" - overrides the style preset's outline/background color
    font_family: str | None = None      # overrides the style preset's font


class ImageOverlay(BaseModel):
    asset_id: str
    s3_key: str
    position: str = "bottom_right"
    opacity: float = 0.85


class TextOverlay(BaseModel):
    """Simple text overlay. Explicit start times are used by editor layers;
    a missing start retains the legacy end-of-video branding behavior."""
    text: str
    duration_seconds: float = 4.0
    position: str = "bottom_center"
    start_seconds: float | None = Field(default=None, ge=0.0)

class RenderManifest(BaseModel):
    project_id: str
    video_tracks: list[VideoTrack]
    output_width: int = 1280
    output_height: int = 720
    frame_rate: int = 24
    target_duration_seconds: float | None = None
    # gap-closure (0006): audio_tracks is now used only for whole-file
    # tracks (music); per-scene voiceover lines go through voice_segments
    # instead, each with its own real start_seconds offset.
    audio_tracks: list[AudioTrack] = []
    voice_segments: list[VoiceSegment] = []
    caption_track: CaptionTrack | None = None
    overlays: list[ImageOverlay] = []
    text_overlays: list[TextOverlay] = []
    output_s3_key: str
