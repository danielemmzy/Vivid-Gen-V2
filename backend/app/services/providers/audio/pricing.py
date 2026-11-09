"""Transparent audio estimate math used for preflight and production reservations.

Defaults match current public endpoint rates and remain configurable in settings.
Self-hosted Chatterbox uses the hosted rate as a conservative proxy until the
operator measures GPU/CPU seconds and changes AUDIO_CHATTERBOX_USD_PER_1000_CHARS.
"""
from __future__ import annotations

from math import ceil
from typing import Any

from app.core.config import settings


def estimate_audio_cost(plan: Any, *, brand_music_available: bool = False) -> dict[str, Any]:
    voice_chars = 0
    provider_cost = 0.0
    provider = getattr(plan.voiceover, "provider", None) or settings.tts_provider
    if plan.voiceover.enabled:
        voice_chars = sum(len((scene.voiceover_line or "").strip()) for scene in plan.scenes)
        rate = settings.audio_chatterbox_usd_per_1000_chars if provider in {"fal_chatterbox", "chatterbox"} else settings.audio_tts_usd_per_1000_chars
        provider_cost += (voice_chars / 1000.0) * rate
    music_generated = bool(plan.music.enabled and not brand_music_available)
    ambience_generated = bool(plan.ambience.enabled)
    if music_generated:
        provider_cost += settings.audio_bed_usd_per_generation
    if ambience_generated:
        provider_cost += settings.audio_bed_usd_per_generation
    retail_usd = provider_cost * settings.audio_retail_markup_multiplier
    credits = ceil(retail_usd / settings.credit_usd_value) if retail_usd > 0 else 0
    return {
        "provider_cost_usd": round(provider_cost, 6),
        "retail_estimate_usd": round(retail_usd, 4),
        "estimated_credits": credits,
        "narration_characters": voice_chars,
        "narration_provider": provider,
        "music_generation_count": int(music_generated),
        "ambience_generation_count": int(ambience_generated),
        "assumptions": {
            "chatterbox_usd_per_1000_chars": settings.audio_chatterbox_usd_per_1000_chars,
            "other_tts_usd_per_1000_chars": settings.audio_tts_usd_per_1000_chars,
            "bed_usd_per_generation": settings.audio_bed_usd_per_generation,
            "retail_markup_multiplier": settings.audio_retail_markup_multiplier,
            "brand_music_is_not_charged_for_generation": True,
        },
    }
