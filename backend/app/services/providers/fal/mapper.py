"""Request-side mapping: internal generation params -> fal.ai argument
shape. This is the one place that knows fal's argument names, so if fal
renames a field, only this file changes."""
from typing import Any

from app.core.exceptions import InvalidGenerationParamsError
from app.services.providers.fal.catalog import get_model


def build_arguments(
    model_id: str,
    generation_type: str,
    *,
    prompt: str | None = None,
    input_url: str | None = None,
    secondary_input_url: str | None = None,
    duration_seconds: int | None = None,
    resolution: str | None = None,
    aspect_ratio: str | None = None,
    num_images: int = 1,
    target_language: str | None = None,
    voice_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    model = get_model(model_id)
    if model["type"] != generation_type:
        raise InvalidGenerationParamsError(
            f"Model {model_id} does not support {generation_type}",
            details={"model_id": model_id, "requested_type": generation_type},
        )

    args: dict[str, Any] = {}
    if generation_type == "text_to_image":
        args = {"prompt": prompt, "num_images": num_images, "aspect_ratio": aspect_ratio or "1:1"}
    elif generation_type == "image_to_image":
        args = {"prompt": prompt, "image_url": input_url}
    elif generation_type == "text_to_video":
        args = {"prompt": prompt, "duration": str(duration_seconds or 5), "resolution": resolution or "720p", "aspect_ratio": aspect_ratio or "16:9"}
    elif generation_type == "image_to_video":
        args = {"prompt": prompt, "image_url": input_url, "duration": str(duration_seconds or 5), "resolution": resolution or "720p"}
    elif generation_type == "avatar":
        args = {"image_url": input_url, "audio_url": secondary_input_url}
    elif generation_type == "video_translation":
        args = {"video_url": input_url, "target_language": target_language or "en"}
    elif generation_type == "audio_replace":
        args = {"video_url": input_url, "audio_url": secondary_input_url}
    elif generation_type == "text_to_speech":
        args = {"text": prompt, "voice_id": voice_id}
    else:
        raise InvalidGenerationParamsError(f"Unsupported generation type: {generation_type}")

    return model["provider_model_id"], {k: v for k, v in args.items() if v is not None}
