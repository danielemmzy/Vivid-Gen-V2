"""Single capability contract for generation models.

The catalog is the source of truth for API validation, pricing estimates and UI
choices. Capabilities are conservative: an option is exposed only when the
provider contract or the self-hosted worker has been verified to support it.
"""
from __future__ import annotations

from typing import Any

from app.core.exceptions import InvalidGenerationParamsError

# Exact capabilities are intentionally explicit. In particular, Wan TI2V-5B
# is not advertised as arbitrary-duration video just because the API accepts an
# integer duration, and Kling 2.5 is limited to its documented 5/10s options.
_CAPABILITIES: dict[str, dict[str, Any]] = {
    "seedream-v4": {"resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16"], "resolution_mode": "preset_based", "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": False},
    "flux-2-turbo": {"resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"], "resolution_mode": "preset_based", "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": False},
    "flux-2": {"resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"], "resolution_mode": "preset_based", "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": False},
    "flux-2-turbo-edit": {"resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"], "audio_input": False, "audio_output": False, "image_input": True, "movie_shots": False, "resolution_mode": "preset_based"},
    "flux-kontext-pro": {"resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"], "audio_input": False, "audio_output": False, "image_input": True, "movie_shots": False, "resolution_mode": "preset_based"},
    "wan-2.5": {"resolutions": ["1080p"], "duration_options": [5], "aspect_ratios": ["16:9", "9:16"], "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": True},
    "wan-2.2-ti2v-5b": {"resolutions": ["420p", "720p"], "duration_options": [5], "aspect_ratios": ["16:9", "9:16"], "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": True, "resolution_mode": "postprocess_output", "provider_resolution": "720p", "inference_parameters": {"sampling_steps": {"supported": True, "default": 20, "minimum": 1, "maximum": 50, "source": "WAN_SAMPLE_STEPS", "benchmark_status": "speed_test_pending_quality_review"}}},
    "wan-2.2-ti2v-5b-i2v": {"resolutions": ["420p", "720p"], "duration_options": [5], "aspect_ratios": ["16:9", "9:16"], "audio_input": False, "audio_output": False, "image_input": True, "movie_shots": True, "resolution_mode": "postprocess_output", "provider_resolution": "720p", "inference_parameters": {"sampling_steps": {"supported": True, "default": 20, "minimum": 1, "maximum": 50, "source": "WAN_SAMPLE_STEPS", "benchmark_status": "speed_test_pending_quality_review"}}},
    "kling-2.5-turbo-pro-i2v": {"resolutions": ["420p", "720p"], "duration_options": [5, 10], "aspect_ratios": [], "audio_input": False, "audio_output": False, "image_input": True, "movie_shots": True, "resolution_mode": "postprocess_output", "provider_resolution": "provider_native"},
    "kling-2.5-turbo-pro": {"resolutions": ["420p", "720p"], "duration_options": [5, 10], "aspect_ratios": ["16:9", "9:16", "1:1"], "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": True, "resolution_mode": "postprocess_output", "provider_resolution": "provider_native"},
    "omnihuman-1.5": {"resolutions": [], "duration_options": [], "aspect_ratios": ["16:9", "9:16"], "audio_input": True, "audio_output": True, "image_input": True, "movie_shots": False, "resolution_mode": "provider_native"},
    "video-translate-dub": {"resolutions": [], "duration_options": [], "aspect_ratios": [], "audio_input": True, "audio_output": True, "image_input": False, "movie_shots": False, "resolution_mode": "preserve_input"},
    "video-dub-audio-only": {"resolutions": [], "duration_options": [], "aspect_ratios": [], "audio_input": True, "audio_output": True, "image_input": False, "movie_shots": False, "resolution_mode": "preserve_input"},
    "audio-replace": {"resolutions": [], "duration_options": [], "aspect_ratios": [], "audio_input": True, "audio_output": True, "image_input": False, "movie_shots": False, "resolution_mode": "preserve_input"},
    "tts-voice-clone": {"resolutions": [], "duration_options": [], "aspect_ratios": [], "audio_input": False, "audio_output": True, "image_input": False, "movie_shots": False},
}


def get_capabilities(model: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe, immutable-by-convention capability snapshot."""
    model_id = str(model["id"])
    raw = _CAPABILITIES.get(model_id)
    if raw is None:
        # Unknown catalog additions fail closed for media dimensions/duration.
        raw = {"resolutions": [], "duration_options": [], "aspect_ratios": [], "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": bool(model.get("supports_movie_shots"))}
    caps = dict(raw)
    caps.setdefault("inference_parameters", {"sampling_steps": {"supported": False, "reason": "provider adapter does not expose a verified sampling-step parameter"}})
    caps.update({
        "input_type": model.get("type"),
        "pricing_unit": model.get("unit"),
        "pricing_strategy": model.get("cost_strategy", "catalog_unit_price"),
        "cost_estimate_basis": model.get("cost_estimate_basis", "catalog price snapshot"),
        "provider_resolution": caps.get("provider_resolution", "provider_native"),
        "output_resolution_mode": "ffmpeg_scale" if caps.get("resolution_mode") == "postprocess_output" else caps.get("resolution_mode", "provider_native"),
    })
    if caps.get("duration_options"):
        caps["min_duration_seconds"] = min(caps["duration_options"])
        caps["max_duration_seconds"] = max(caps["duration_options"])
    else:
        caps["min_duration_seconds"] = None
        caps["max_duration_seconds"] = None
    return caps


def fallback_preserves_framing(
    source_model: dict[str, Any], candidate_model: dict[str, Any], *,
    generation_type: str, aspect_ratio: str | None,
) -> bool:
    """Prevent fallback from silently changing image-derived framing.

    Kling I2V derives its aspect ratio from the uploaded image. If the request
    did not explicitly select a ratio, falling back to a model that requires a
    16:9/9:16 override could silently change composition, so we fail closed.
    """
    if generation_type != "image_to_video" or aspect_ratio is not None:
        return True
    source_caps = get_capabilities(source_model)
    candidate_caps = get_capabilities(candidate_model)
    return not (not source_caps.get("aspect_ratios") and bool(candidate_caps.get("aspect_ratios")))


def validate_generation_request(
    model: dict[str, Any], *, generation_type: str, duration_seconds: float | None = None,
    resolution: str | None = None, aspect_ratio: str | None = None, has_image_input: bool = False,
    has_audio_input: bool = False,
) -> None:
    """Reject unsupported combinations before reservation or provider submission."""
    if model.get("type") != generation_type:
        raise InvalidGenerationParamsError(
            f"Model {model['id']} does not support {generation_type}",
            details={"model_id": model["id"], "requested_type": generation_type},
        )
    caps = get_capabilities(model)
    if duration_seconds is not None and caps["duration_options"] and int(duration_seconds) not in caps["duration_options"]:
        raise InvalidGenerationParamsError(
            f"{model['name']} supports only {', '.join(str(v) + 's' for v in caps['duration_options'])}",
            details={"model_id": model["id"], "duration_options": caps["duration_options"]},
        )
    if duration_seconds is not None and not caps["duration_options"] and generation_type in ("text_to_video", "image_to_video"):
        raise InvalidGenerationParamsError(
            f"Duration support is not configured for {model['name']}",
            details={"model_id": model["id"], "reason": "duration_capability_missing"},
        )
    if resolution is not None and generation_type in ("text_to_video", "image_to_video") and resolution not in caps["resolutions"]:
        raise InvalidGenerationParamsError(
            f"{model['name']} supports final output resolutions: {', '.join(caps['resolutions']) or 'provider-native only'}",
            details={"model_id": model["id"], "supported_resolutions": caps["resolutions"]},
        )
    if generation_type in ("text_to_video", "image_to_video") and not caps["resolutions"]:
        raise InvalidGenerationParamsError(
            f"Selectable output resolution is not configured for {model['name']}",
            details={"model_id": model["id"], "reason": "resolution_capability_missing"},
        )
    if aspect_ratio and generation_type in ("text_to_video", "image_to_video") and not caps["aspect_ratios"]:
        raise InvalidGenerationParamsError(
            f"{model['name']} derives framing from its input and does not accept an aspect-ratio override",
            details={"model_id": model["id"], "reason": "aspect_ratio_not_selectable"},
        )
    if aspect_ratio and caps["aspect_ratios"] and aspect_ratio not in caps["aspect_ratios"]:
        raise InvalidGenerationParamsError(
            f"{model['name']} does not support aspect ratio {aspect_ratio}",
            details={"model_id": model["id"], "supported_aspect_ratios": caps["aspect_ratios"]},
        )
    if has_image_input and not caps["image_input"]:
        raise InvalidGenerationParamsError(f"{model['name']} does not accept image input", details={"model_id": model["id"]})
    if has_audio_input and not caps["audio_input"]:
        raise InvalidGenerationParamsError(f"{model['name']} does not accept audio input", details={"model_id": model["id"]})
