from datetime import datetime
from typing import Literal

QualityMode = Literal["low", "medium", "high"]

from pydantic import BaseModel, Field, model_validator

GenerationType = Literal[
    "text_to_image", "image_to_image", "text_to_video", "image_to_video",
    "avatar", "video_translation", "audio_replace", "text_to_speech",
]


class TextToImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    model: str | None = None
    quality_mode: QualityMode = "medium"
    aspect_ratio: str = "1:1"
    num_images: int = Field(default=1, ge=1, le=4)


class ImageToImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    input_s3_key: str = Field(min_length=1, max_length=1024)
    model: str | None = None
    quality_mode: QualityMode = "medium"


class TextToVideoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    model: str | None = None
    quality_mode: QualityMode = "medium"
    duration_seconds: Literal[5, 10] = 5
    resolution: Literal["420p", "720p"] = "720p"
    aspect_ratio: str = "16:9"


class ImageToVideoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    input_s3_key: str = Field(min_length=1, max_length=1024)
    model: str | None = None
    quality_mode: QualityMode = "medium"
    duration_seconds: Literal[5, 10] = 5
    resolution: Literal["420p", "720p"] = "720p"
    aspect_ratio: str | None = None


class AvatarRequest(BaseModel):
    """Talking-photo / lip-sync generation: a still image animated to speak
    the given audio track. If known, the source audio duration tightens the
    reservation estimate; otherwise the configured conservative default is used."""
    image_s3_key: str = Field(min_length=1, max_length=1024)
    audio_s3_key: str = Field(min_length=1, max_length=1024)
    duration_seconds: int | None = Field(default=None, ge=1, le=900)
    model: str = "omnihuman-1.5"


class VideoTranslationRequest(BaseModel):
    """Translate + optionally lip-sync an existing video into another language."""
    video_s3_key: str = Field(min_length=1, max_length=1024)
    target_language: str = Field(min_length=2, max_length=10)
    source_duration_seconds: int | None = Field(default=None, ge=1, le=900)
    lip_sync: bool = True
    model: str | None = None  # resolved to video-translate-dub / video-dub-audio-only if omitted


class AudioReplaceRequest(BaseModel):
    video_s3_key: str = Field(min_length=1, max_length=1024)
    audio_s3_key: str = Field(min_length=1, max_length=1024)
    source_duration_seconds: int | None = Field(default=None, ge=1, le=900)
    model: str = "audio-replace"


class GenerationEstimateRequest(BaseModel):
    """A non-mutating quote; creating the generation revalidates and reserves atomically."""
    generation_type: GenerationType
    model_id: str | None = None
    quality_mode: QualityMode = "medium"
    duration_seconds: int | None = Field(default=None, ge=1, le=900)
    resolution: str | None = None
    aspect_ratio: str | None = None
    num_images: int = Field(default=1, ge=1, le=4)

    @model_validator(mode="after")
    def validate_video_duration_options(self):
        if self.generation_type in ("text_to_video", "image_to_video") and self.duration_seconds is not None and self.duration_seconds not in (5, 10):
            raise ValueError("Video duration must be one of the supported options: 5 or 10 seconds")
        if self.generation_type in ("text_to_video", "image_to_video") and self.resolution is not None and self.resolution not in ("420p", "720p"):
            raise ValueError("Video output resolution must be 420p or 720p")
        return self


class ProductionEstimateRequest(BaseModel):
    """Quote a finished production runtime, not a single model inference."""
    generation_type: Literal["text_to_video", "image_to_video"]
    target_duration_seconds: int = Field(ge=5, le=600)
    quality_mode: QualityMode = "medium"
    model_id: str | None = None
    resolution: Literal["420p", "720p"] = "720p"
    aspect_ratio: str = "16:9"


class ProductionEstimateResponse(BaseModel):
    generation_type: str
    target_duration_seconds: int
    model_id: str
    model_name: str
    provider: str
    provider_model_id: str
    quality_tier: str
    resolution: str
    max_shot_duration_seconds: int
    shot_count: int
    scene_count_estimate: int
    billable_generation_seconds: int
    estimated_provider_cost_usd: float
    credits_to_reserve: int
    credit_usd_value: float
    pricing_strategy: str
    cost_estimate_basis: str
    cost_rate_version: str | None = None
    capabilities: dict
    included: list[str]
    excluded: list[str]
    note: str


class GenerationEstimateResponse(BaseModel):
    generation_type: str
    model_id: str
    model_name: str
    provider: str
    provider_model_id: str
    quality_tier: str
    duration_seconds: int | None = None
    resolution: str | None = None
    estimated_provider_cost_usd: float
    estimated_reservation_cost_usd: float
    credits_to_reserve: int
    credit_usd_value: float
    pricing_strategy: str
    cost_estimate_basis: str
    cost_rate_version: str | None = None
    capabilities: dict
    note: str | None = None


class GenerationResponse(BaseModel):
    id: str
    status: str
    type: str
    model_id: str
    duration_seconds: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    title: str | None = None
    credits_reserved: int
    credits_charged: int = 0
    estimated_provider_cost_usd: float
    actual_provider_cost_usd: float | None = None
    actual_cost_source: str | None = None
    retry_count: int = 0
    output_url: str | None = None
    thumbnail_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None


class RenameGenerationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class GenerationListResponse(BaseModel):
    generations: list[GenerationResponse]
    limit: int
    offset: int
