"""V2: the structured output contract for the AI Director (planner.py).

These schemas are what the LLM is asked to fill in, and what the executor
(executor.py) reads to create real Character/Shot rows via the existing
MovieService. Nothing here is persisted as new database columns yet —
Phase 2's audit found no evidence a new parallel Scene/Job table is
needed, so a ProductionPlan is stored as a single JSON blob (see the
`production_plan` column added to `Project` in this phase's migration)
and re-expanded into real Shots at approval time, not before.

Field-by-field, this is the structured contract between the AI Director
and the production executor. The executor turns each requested scene duration
into model-supported clip jobs, trims the final clip to the scene timeline,
and persists continuity dependencies before execution.
"""
from typing import Literal

from pydantic import BaseModel, Field

VisualType = Literal["generated_video", "generated_image", "stock_video", "stock_image", "user_asset", "text_graphic"]
QualityMode = Literal["low", "medium", "high", "fast", "balanced", "best"]
ContinuityMode = Literal["none", "character", "previous_final_frame", "scene_reference"]
BudgetProfile = Literal["short_form", "long_form"]


class ScenePlan(BaseModel):
    scene_number: int
    duration_seconds: int = Field(ge=2, le=30)
    purpose: str  # e.g. "hook", "product", "lifestyle", "brand", "cta", "b-roll"
    visual_type: VisualType = "generated_video"
    visual_prompt: str
    voiceover_line: str | None = None
    camera_notes: str | None = None
    requires_character_reference: bool = False
    requires_product_reference: bool = False
    # gap-closure: previously these two `requires_*_reference` booleans
    # were declared and read nowhere — executor.py never passed any
    # character/reference into a generated scene regardless of their
    # value. `character_id` is what actually closes that: the Director is
    # now told which Characters already exist on this project (see
    # planner.py's `existing_characters` param) and can name one here,
    # which the executor passes straight into MovieService.add_shot's
    # character_ids.
    character_id: str | None = None
    # Round 4, decision #2 (confirmed): Product is now its own
    # first-class entity (models/product.py), not a Character reused to
    # hold product photos — set this instead of character_id when
    # requires_product_reference is true. See orchestration/
    # asset_router.py::resolve_reference_image for how this actually
    # reaches generation.
    product_id: str | None = None
    # Round 4, decision #5 (confirmed): real scene-to-scene continuity —
    # set ONLY when this scene genuinely needs an earlier scene's ACTUAL
    # generated output as its image reference (e.g. "continue from where
    # scene 1 left off"), never invented to demonstrate a DAG edge. When
    # set, executor.py adds a real dependency edge (this scene's SCENE
    # task cannot become READY until the referenced scene's SCENE task
    # COMPLETEs) and the generation is conditioned on that scene's actual
    # output frame, not a static asset — see asset_router.py::
    # resolve_reference_image. plan_validator.py checks the referenced
    # scene_number exists and precedes this one.
    reference_scene_number: int | None = None
    # Explicit continuity policy; reference_scene_number remains the exact dependency when supplied.
    continuity_mode: ContinuityMode = "none"
    # gap-closure: minimal Asset Router (P0.5) — when visual_type is
    # "user_asset", this must be a S3 key the user already uploaded
    # (e.g. via POST /uploads/presign). executor.py then creates the shot
    # as a pass-through (no generation submitted, no credits spent) that
    # points directly at this asset — see MovieService.add_user_asset_shot.
    source_asset_s3_key: str | None = None
    # gap-closure (0006), extended round 4: when set, a specific known
    # URL is fetched directly (orchestration/asset_fetch.py,
    # AssetSourceType.STOCK_URL). When visual_type is "stock_video"/
    # "stock_image" and this is UNSET, orchestration/asset_router.py now
    # does a real keyword search (AssetSourceType.STOCK_SEARCH) against
    # a configured StockProvider instead of requiring a URL — the URL
    # path remains available as a separate, explicit source, not
    # replaced.
    stock_source_url: str | None = None
    # Imported, user-owned still image used to condition this generated shot.
    # Keys are accepted only from the user's uploads/*/url-reference, ppt-reference or media-reference prefixes.
    reference_image_s3_key: str | None = None
    source_license: str | None = None
    source_attribution: str | None = None
    source_provider: str | None = None
    source_external_id: str | None = None


class VoicePlan(BaseModel):
    enabled: bool = False
    style: str | None = None  # e.g. "confident", "warm", "energetic" — passed to compatible TTS providers
    voice_id: str | None = None  # a Character.voice_id or provider-specific voice identifier
    # fal_chatterbox is the managed low-cost endpoint; chatterbox is a separately deployed endpoint.
    provider: Literal["fal", "elevenlabs", "chatterbox", "fal_chatterbox"] | None = None
    # User-owned uploaded/recorded voice reference; kept as an S3 key, never a client-supplied public URL.
    reference_audio_s3_key: str | None = None
    volume: float = Field(default=1.0, ge=0.0, le=2.0)


class MusicPlan(BaseModel):
    enabled: bool = False
    mood: str | None = None
    genre: str | None = None
    provider: Literal["fal"] | None = None  # None uses AUDIO_GENERATION_PROVIDER
    start_seconds: float = Field(default=0.0, ge=0.0, le=600.0)
    duration_seconds: int | None = Field(default=None, ge=1, le=600)
    volume: float = Field(default=0.22, ge=0.0, le=2.0)
    fade_in_seconds: float = Field(default=1.0, ge=0.0, le=30.0)
    fade_out_seconds: float = Field(default=2.0, ge=0.0, le=30.0)
    loop: bool = True


class AmbiencePlan(BaseModel):
    enabled: bool = False
    prompt: str | None = None
    provider: Literal["fal"] | None = None  # None uses AUDIO_GENERATION_PROVIDER
    start_seconds: float = Field(default=0.0, ge=0.0, le=600.0)
    duration_seconds: int | None = Field(default=None, ge=1, le=600)
    volume: float = Field(default=0.18, ge=0.0, le=2.0)
    fade_in_seconds: float = Field(default=0.5, ge=0.0, le=30.0)
    fade_out_seconds: float = Field(default=1.0, ge=0.0, le=30.0)
    loop: bool = True


class CaptionPlan(BaseModel):
    enabled: bool = False
    style: Literal["minimal", "creator", "bold", "cinematic", "corporate"] = "minimal"


class BrandingPlan(BaseModel):
    enabled: bool = False
    brand_kit_id: str | None = None


class ProductionPlan(BaseModel):
    """The AI Director's complete output for one project. Never call a
    provider directly from here — see planner.py's module docstring for
    why the Director -> Plan -> Executor -> Provider separation matters."""

    project_type: str  # "video" | "advertisement" | "youtube" | "short" | "product_video" | "podcast" | ...
    title: str
    duration_seconds: int = Field(ge=5, le=600)
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    target_platform: str | None = None
    language: str = "en"
    style: str | None = None
    audience: str | None = None
    goal: str | None = None
    quality_mode: QualityMode = "medium"
    # User preference for the video engine. Auto uses quality/health/cost routing.
    # WAN and Kling are preferences; routing may fall back if the provider is not configured.
    video_engine: Literal["auto", "wan", "kling"] = "auto"
    # Short form: <=60s / <=20 shots / one user-initiated retry per shot.
    # Long form: <=600s / <=160 shots / two retries per shot. Credits are still estimated from actual models.
    budget_profile: BudgetProfile | None = None

    script: str | None = None
    scenes: list[ScenePlan] = Field(min_length=1, max_length=20)

    voiceover: VoicePlan = VoicePlan()
    music: MusicPlan = MusicPlan()
    ambience: AmbiencePlan = AmbiencePlan()
    captions: CaptionPlan = CaptionPlan()
    branding: BrandingPlan = BrandingPlan()

    def total_scene_seconds(self) -> int:
        return sum(s.duration_seconds for s in self.scenes)
