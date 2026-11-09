"""Canonical commercial model catalog.

Provider costs are estimates/snapshots used for credit reservation. They are
not the customer price; `retail_multiplier` turns provider cost into credits.
The database migration 0009 mirrors these entries so historical generations
remain referentially stable while the application catalog stays readable.
"""
from typing import Any

MODELS: dict[str, dict[str, Any]] = {
    # Deprecated entries stay readable for in-flight/historical generations,
    # but are excluded from the public model catalog and routing.
    "seedream-v4": {
        "id": "seedream-v4", "quality_tier": "economy", "provider": "fal",
        "provider_model_id": "fal-ai/bytedance/seedream/v4/text-to-image", "name": "Seedream V4 (legacy)",
        "type": "text_to_image", "unit": "image", "price": 0.03, "retail_multiplier": 2.5,
        "max_resolution": "2048x2048", "supports_movie_shots": False, "enabled": False,
    },
    # --- Images ---
    "flux-2-turbo": {
        "id": "flux-2-turbo", "quality_tier": "economy", "provider": "fal",
        "provider_model_id": "fal-ai/flux-2/turbo", "name": "FLUX.2 Turbo",
        "type": "text_to_image", "unit": "image", "price": 0.008,
        "retail_multiplier": 2.5, "max_resolution": "2048x2048", "supports_movie_shots": False,
    },
    "flux-2": {
        "id": "flux-2", "quality_tier": "standard", "provider": "fal",
        "provider_model_id": "fal-ai/flux-2", "name": "FLUX.2",
        "type": "text_to_image", "unit": "image", "price": 0.012,
        "retail_multiplier": 2.5, "max_resolution": "2048x2048", "supports_movie_shots": False,
    },
    "flux-2-turbo-edit": {
        "id": "flux-2-turbo-edit", "quality_tier": "economy", "provider": "fal",
        "provider_model_id": "fal-ai/flux-2/turbo/edit", "name": "FLUX.2 Turbo Edit",
        "type": "image_to_image", "unit": "image", "price": 0.016,
        "retail_multiplier": 2.5, "max_resolution": "2048x2048", "supports_movie_shots": False,
    },
    "flux-kontext-pro": {
        "id": "flux-kontext-pro", "quality_tier": "premium", "provider": "fal",
        "provider_model_id": "fal-ai/flux-pro/kontext", "name": "FLUX Kontext Pro",
        "type": "image_to_image", "unit": "image", "price": 0.04,
        "retail_multiplier": 2.5, "max_resolution": "2048x2048", "supports_movie_shots": False,
    },
    # --- Video ---
    "wan-2.5": {
        "id": "wan-2.5", "quality_tier": "standard", "provider": "fal",
        "provider_model_id": "fal-ai/wan-25-preview/text-to-video", "name": "Wan 2.5 (legacy)",
        "type": "text_to_video", "unit": "second", "price": 0.05, "retail_multiplier": 2.5,
        "max_resolution": "1080p", "supports_movie_shots": True, "enabled": False,
    },
    "wan-2.2-ti2v-5b": {
        "id": "wan-2.2-ti2v-5b", "quality_tier": "economy", "provider": "modal",
        "provider_model_id": "wan2.2-ti2v-5b", "name": "Wan 2.2 TI2V-5B (Modal)",
        "type": "text_to_video", "unit": "second", "price": 0.06,
        "retail_multiplier": 2.0, "max_resolution": "720p", "supports_movie_shots": True,
        "cost_strategy": "modal_runtime_estimate", "cost_estimate_basis": "estimated Modal runtime using published GPU/CPU/memory rates; not invoice-reconciled",
    },
    "wan-2.2-ti2v-5b-i2v": {
        "id": "wan-2.2-ti2v-5b-i2v", "quality_tier": "economy", "provider": "modal",
        "provider_model_id": "wan2.2-ti2v-5b-i2v", "name": "Wan 2.2 TI2V-5B I2V (Modal)",
        "type": "image_to_video", "unit": "second", "price": 0.06,
        "retail_multiplier": 2.0, "max_resolution": "720p", "supports_movie_shots": True,
        "cost_strategy": "modal_runtime_estimate", "cost_estimate_basis": "estimated Modal runtime using published GPU/CPU/memory rates; not invoice-reconciled",
    },
    "kling-2.5-turbo-pro-i2v": {
        "id": "kling-2.5-turbo-pro-i2v", "quality_tier": "premium", "provider": "fal",
        "provider_model_id": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        "name": "Kling 2.5 Turbo Pro I2V", "type": "image_to_video", "unit": "second", "price": 0.07,
        "retail_multiplier": 2.5, "max_resolution": "720p", "supports_movie_shots": True,
    },
    "kling-2.5-turbo-pro": {
        "id": "kling-2.5-turbo-pro", "quality_tier": "premium", "provider": "fal",
        "provider_model_id": "fal-ai/kling-video/v2.5-turbo/pro/text-to-video",
        "name": "Kling 2.5 Turbo Pro", "type": "text_to_video", "unit": "second", "price": 0.07,
        "retail_multiplier": 2.5, "max_resolution": "720p", "supports_movie_shots": True,
    },
    # --- Avatar / dubbing / audio ---
    "omnihuman-1.5": {
        "id": "omnihuman-1.5", "quality_tier": "premium", "provider": "fal",
        "provider_model_id": "fal-ai/bytedance/omnihuman/v1.5", "name": "Omnihuman 1.5",
        "type": "avatar", "unit": "second", "price": 0.16, "retail_multiplier": 2.5,
        "max_resolution": "1080p", "supports_movie_shots": False,
    },
    "video-translate-dub": {
        "id": "video-translate-dub", "quality_tier": "premium", "provider": "fal",
        "provider_model_id": "fal-ai/video-translate/dub-lipsync", "name": "Video Translate + Lip-sync",
        "type": "video_translation", "unit": "minute", "price": 0.35, "retail_multiplier": 2.5,
        "max_resolution": "1080p", "supports_movie_shots": False,
    },
    "video-dub-audio-only": {
        "id": "video-dub-audio-only", "quality_tier": "standard", "provider": "fal",
        "provider_model_id": "fal-ai/video-translate/dub-audio-only", "name": "Audio-only Dub",
        "type": "video_translation", "unit": "minute", "price": 0.14, "retail_multiplier": 2.5,
        "max_resolution": "1080p", "supports_movie_shots": False,
    },
    "audio-replace": {
        "id": "audio-replace", "quality_tier": "standard", "provider": "fal",
        "provider_model_id": "fal-ai/video-audio/replace", "name": "Replace Video Audio",
        "type": "audio_replace", "unit": "minute", "price": 0.10, "retail_multiplier": 2.5,
        "max_resolution": "1080p", "supports_movie_shots": False,
    },
    "tts-voice-clone": {
        "id": "tts-voice-clone", "quality_tier": "standard", "provider": "fal",
        "provider_model_id": "fal-ai/elevenlabs/tts/turbo-v2.5", "name": "Voice Clone TTS",
        "type": "text_to_speech", "unit": "minute", "price": 0.06, "retail_multiplier": 2.5,
        "max_resolution": None, "supports_movie_shots": False,
    },
}


def get_model(model_id: str) -> dict[str, Any]:
    try:
        return MODELS[model_id]
    except KeyError as exc:
        from app.core.exceptions import ModelNotFoundError
        raise ModelNotFoundError(f"Unsupported model: {model_id}", details={"model_id": model_id}) from exc


def models_for_type(generation_type: str) -> list[dict[str, Any]]:
    return [m for m in MODELS.values() if m.get("enabled", True) and m["type"] == generation_type]


def movie_shot_models() -> list[dict[str, Any]]:
    return [m for m in MODELS.values() if m.get("enabled", True) and m.get("supports_movie_shots")]


# Attach an explicit capability contract to every entry, including disabled
# legacy models. Public catalog, estimator and generation validation consume
# this same object rather than maintaining independent UI assumptions.
from app.services.generation.capabilities import get_capabilities as _get_capabilities
for _model in MODELS.values():
    _model["capabilities"] = _get_capabilities(_model)
