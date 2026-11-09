"""Provider-specific argument mapping.

Keep provider API shapes here; GenerationService should not know whether an
image model calls its aspect-ratio field `image_size`, `image_urls`, etc.
"""
from typing import Any
from app.core.exceptions import InvalidGenerationParamsError
from app.services.providers.fal.catalog import get_model

_ASPECT_TO_IMAGE_SIZE = {
    "1:1": "square_hd",
    "16:9": "landscape_16_9",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
    "3:4": "portrait_4_3",
}


def build_arguments(
    model_id: str, generation_type: str, *, prompt: str | None = None, input_url: str | None = None,
    secondary_input_url: str | None = None, duration_seconds: int | None = None, resolution: str | None = None,
    aspect_ratio: str | None = None, num_images: int = 1, target_language: str | None = None,
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
        if model_id.startswith("flux-2"):
            args = {
                "image_size": _ASPECT_TO_IMAGE_SIZE.get(aspect_ratio or "1:1", "square_hd"),
                "num_images": num_images,
                "guidance_scale": 2.5,
                "enable_safety_checker": True,
                "output_format": "png",
            }
        else:
            # Keep the generic provider mapping self-describing. FalProvider
            # also injects `prompt`; the same value wins there, preserving
            # the endpoint payload while keeping direct mapper consumers sane.
            args = {"prompt": prompt, "num_images": num_images, "aspect_ratio": aspect_ratio or "1:1"}
    elif generation_type == "image_to_image":
        if model_id == "flux-2-turbo-edit":
            args = {"image_urls": [input_url], "image_size": "square_hd", "num_images": 1, "enable_safety_checker": True, "output_format": "png"}
        else:
            args = {"image_url": input_url}
    elif generation_type == "text_to_video":
        from app.services.generation.capabilities import get_capabilities
        caps = get_capabilities(model)
        provider_resolution = caps.get("provider_resolution", "provider_native")
        if model_id.startswith("kling-2.5") or provider_resolution == "provider_native":
            # Kling accepts duration/aspect ratio but not a resolution input.
            # `resolution` is the final export target; never forward it as an
            # unsupported provider argument.
            args = {"duration": str(duration_seconds or 5), "aspect_ratio": aspect_ratio or "16:9"}
        else:
            args = {"duration": str(duration_seconds or 5), "resolution": provider_resolution, "aspect_ratio": aspect_ratio or "16:9"}
    elif generation_type == "image_to_video":
        from app.services.generation.capabilities import get_capabilities
        caps = get_capabilities(model)
        provider_resolution = caps.get("provider_resolution", "provider_native")
        if model_id.startswith("kling-2.5") or provider_resolution == "provider_native":
            args = {"duration": str(duration_seconds or 5)}
        else:
            args = {"duration": str(duration_seconds or 5), "resolution": provider_resolution, "aspect_ratio": aspect_ratio or "16:9"}
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
