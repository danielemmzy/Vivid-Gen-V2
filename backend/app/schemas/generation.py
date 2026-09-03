from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

GenerationType = Literal[
    "text_to_image", "image_to_image", "text_to_video", "image_to_video",
    "avatar", "video_translation", "audio_replace",
]


class TextToImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    model: str = "seedream-v4"
    aspect_ratio: str = "1:1"
    num_images: int = Field(default=1, ge=1, le=4)


class ImageToImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    input_s3_key: str = Field(min_length=1, max_length=1024)
    model: str = "flux-kontext-pro"


class TextToVideoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    model: str = "wan-2.5"
    duration_seconds: int = Field(default=5, ge=5, le=30)
    resolution: Literal["480p", "720p", "1080p"] = "720p"
    aspect_ratio: str = "16:9"


class ImageToVideoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    input_s3_key: str = Field(min_length=1, max_length=1024)
    model: str = "kling-2.5-turbo-pro-i2v"
    duration_seconds: int = Field(default=5, ge=5, le=30)
    resolution: Literal["480p", "720p", "1080p"] = "720p"


class AvatarRequest(BaseModel):
    """Talking-photo / lip-sync generation: a still image animated to speak
    the given audio track."""
    image_s3_key: str = Field(min_length=1, max_length=1024)
    audio_s3_key: str = Field(min_length=1, max_length=1024)
    resolution: Literal["720p", "1080p"] = "720p"
    model: str = "omnihuman-1.5"


class VideoTranslationRequest(BaseModel):
    """HeyGen-equivalent: translate + optionally lip-sync an existing video
    into another language."""
    video_s3_key: str = Field(min_length=1, max_length=1024)
    target_language: str = Field(min_length=2, max_length=10)
    lip_sync: bool = True
    model: str | None = None  # resolved to video-translate-dub / video-dub-audio-only if omitted


class AudioReplaceRequest(BaseModel):
    video_s3_key: str = Field(min_length=1, max_length=1024)
    audio_s3_key: str = Field(min_length=1, max_length=1024)
    model: str = "audio-replace"


class GenerationResponse(BaseModel):
    id: str
    status: str
    type: str
    model_id: str
    title: str | None = None
    credits_reserved: int
    credits_charged: int = 0
    estimated_provider_cost_usd: float
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
