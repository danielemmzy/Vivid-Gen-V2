"""Model catalog. Provider pricing snapshot from fal's public pricing page,
2026-08-19 — treat as configurable commercial policy, not immutable truth.
This is the seed data for the `ai_model` table (see alembic/versions for the
data migration); services read it via AIModelRepository once seeded, but we
keep the raw dict here as the single place a human edits when fal changes
prices or a new model ships, rather than hand-writing SQL.

Extended beyond the original four generation types to cover every mode a
HeyGen/Runway/Kling-class product needs: avatar/lip-sync, video translation
+ dubbing, audio replacement, and movie-shot generation (same models as
text/image-to-video, tagged `supports_movie_shots` for the storyboard
feature in services/movie/)."""
from typing import Any

MODELS: dict[str, dict[str, Any]] = {
    # --- Images ---
    "seedream-v4": {
        "id": "seedream-v4", "provider_model_id": "fal-ai/bytedance/seedream/v4/text-to-image",
        "name": "Seedream V4", "type": "text_to_image", "unit": "image", "price": 0.03,
        "max_resolution": "2048x2048", "supports_movie_shots": False,
    },
    "flux-kontext-pro": {
        "id": "flux-kontext-pro", "provider_model_id": "fal-ai/flux-pro/kontext",
        "name": "Flux Kontext Pro", "type": "image_to_image", "unit": "image", "price": 0.04,
        "max_resolution": "2048x2048", "supports_movie_shots": False,
    },
    # --- Video ---
    "wan-2.5": {
        "id": "wan-2.5", "provider_model_id": "fal-ai/wan-25-preview/text-to-video",
        "name": "Wan 2.5", "type": "text_to_video", "unit": "second", "price": 0.05,
        "max_resolution": "1080p", "supports_movie_shots": True,
    },
    "kling-2.5-turbo-pro-i2v": {
        "id": "kling-2.5-turbo-pro-i2v", "provider_model_id": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        "name": "Kling 2.5 Turbo Pro I2V", "type": "image_to_video", "unit": "second", "price": 0.07,
        "max_resolution": "1080p", "supports_movie_shots": True,
    },
    "kling-2.5-turbo-pro": {
        "id": "kling-2.5-turbo-pro", "provider_model_id": "fal-ai/kling-video/v2.5-turbo/pro/text-to-video",
        "name": "Kling 2.5 Turbo Pro", "type": "text_to_video", "unit": "second", "price": 0.07,
        "max_resolution": "1080p", "supports_movie_shots": True,
    },
    # --- Avatar / talking photo (lip-sync from a still + audio) ---
    "omnihuman-1.5": {
        "id": "omnihuman-1.5", "provider_model_id": "fal-ai/bytedance/omnihuman/v1.5",
        "name": "Omnihuman 1.5", "type": "avatar", "unit": "second", "price": 0.16,
        "max_resolution": "1080p", "supports_movie_shots": False,
    },
    # --- Video translation / dubbing (HeyGen-equivalent) ---
    "video-translate-dub": {
        "id": "video-translate-dub", "provider_model_id": "fal-ai/video-translate/dub-lipsync",
        "name": "Video Translate + Lip-sync", "type": "video_translation", "unit": "minute", "price": 0.35,
        "max_resolution": "1080p", "supports_movie_shots": False,
    },
    "video-dub-audio-only": {
        "id": "video-dub-audio-only", "provider_model_id": "fal-ai/video-translate/dub-audio-only",
        "name": "Audio-only Dub", "type": "video_translation", "unit": "minute", "price": 0.14,
        "max_resolution": "1080p", "supports_movie_shots": False,
    },
    # --- Audio replacement ---
    "audio-replace": {
        "id": "audio-replace", "provider_model_id": "fal-ai/video-audio/replace",
        "name": "Replace Video Audio", "type": "audio_replace", "unit": "minute", "price": 0.10,
        "max_resolution": "1080p", "supports_movie_shots": False,
    },
    # --- Text-to-speech for voice cloning / narration (character.voice_id) ---
    "tts-voice-clone": {
        "id": "tts-voice-clone", "provider_model_id": "fal-ai/elevenlabs/tts/turbo-v2.5",
        "name": "Voice Clone TTS", "type": "text_to_speech", "unit": "minute", "price": 0.06,
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
    return [m for m in MODELS.values() if m["type"] == generation_type]


def movie_shot_models() -> list[dict[str, Any]]:
    return [m for m in MODELS.values() if m.get("supports_movie_shots")]
