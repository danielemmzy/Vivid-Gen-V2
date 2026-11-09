from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get_or_set
from app.core.config import settings
from app.core.exceptions import InvalidGenerationParamsError
from app.core.constants import GenerationType
from app.dependencies import current_user_id, db_session
from app.schemas.generation import (GenerationEstimateRequest, GenerationEstimateResponse, ProductionEstimateRequest, ProductionEstimateResponse)
from app.services.generation.capabilities import get_capabilities, validate_generation_request
from app.services.generation.pricing import calculate_credits, estimate_reservation, provider_cost_usd
from app.services.generation.production_estimate import plan_inference_units, production_shot_count
from app.orchestration.model_router import RoutingRequest, select_with_fallback
from app.services.providers.fal.catalog import MODELS, get_model
from app.services.providers.registry import provider_is_configured

router = APIRouter(prefix="/models", tags=["models"])


def _build_catalog() -> dict:
    result = []
    for m in MODELS.values():
        if not m.get("enabled", True):
            continue
        unit_seconds = 1 if m["unit"] == "second" else 60 if m["unit"] == "minute" else None
        sample_cost = provider_cost_usd(m, duration_seconds=unit_seconds, num_images=1)
        caps = get_capabilities(m)
        example_duration = 5 if 5 in caps.get("duration_options", []) else ((caps.get("duration_options") or [None])[0])
        if m["id"] == "omnihuman-1.5":
            example_duration = settings.avatar_reservation_seconds
        elif m["id"] in ("video-translate-dub", "video-dub-audio-only", "audio-replace"):
            example_duration = settings.unknown_media_reservation_seconds
        result.append({
            **m,
            # `price` is the estimated provider cost per billing unit, not
            # the customer-facing credit price. Modal is computed from runtime
            # and current configured resource rates.
            "price": round(sample_cost, 8),
            "capabilities": caps,
            "provider_configured": provider_is_configured("fake" if settings.generation_provider == "fake" else m["provider"]),
            "credits_per_unit": calculate_credits(sample_cost, markup_multiplier=m.get("retail_multiplier")),
            "cost_estimate_basis": m.get("cost_estimate_basis", "catalog price snapshot; not provider-invoice-reconciled"),
            "example_estimate_credits": estimate_reservation(
                m, duration_seconds=example_duration, num_images=1,
                safety_margin=1.5 if m["id"] == "omnihuman-1.5" else 1.0,
            )[1],
        })
    return {"models": result}


@router.get("")
async def list_models():
    return await cache_get_or_set("vividgen:cache:model_catalog", settings.model_catalog_cache_ttl_seconds, _load_catalog)


@router.post("/estimate-production", response_model=ProductionEstimateResponse)
async def estimate_production(
    body: ProductionEstimateRequest,
    _user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(db_session),
):
    """Estimate a multi-shot finished video using the same conservative
    per-shot billing approach used by the production budget ledger.

    The target runtime may be longer than one inference. Every planned shot
    remains constrained to a verified five-second provider request; the final
    clip is trimmed during assembly. The 420p option is a delivery resize for
    current Wan routes and therefore does not discount inference charges.
    """
    capability = body.generation_type
    if body.model_id:
        model = get_model(body.model_id)
        if not model.get("enabled", True) or model["type"] != capability or not model.get("supports_movie_shots"):
            raise InvalidGenerationParamsError(
                "The selected model cannot be used for this production type.",
                details={"model_id": body.model_id, "generation_type": capability},
            )
        effective_provider = "fake" if settings.generation_provider == "fake" else model["provider"]
        if not provider_is_configured(effective_provider):
            raise InvalidGenerationParamsError(
                f"Provider '{effective_provider}' is not configured.",
                details={"model_id": body.model_id, "provider": effective_provider, "reason": "provider_not_configured"},
            )
    else:
        chain = await select_with_fallback(
            session,
            RoutingRequest(capability=capability, quality_mode=body.quality_mode,
                           require_movie_shot_support=True, duration_seconds=5),
            max_attempts=1,
        )
        if not chain:
            raise InvalidGenerationParamsError(
                f"No configured model is available for {capability} at quality '{body.quality_mode}'.",
                details={"generation_type": capability, "quality_mode": body.quality_mode},
            )
        model = chain[0]

    caps = get_capabilities(model)
    validate_aspect_ratio = body.aspect_ratio
    if capability == "image_to_video" and not caps.get("aspect_ratios"):
        # Some image-to-video models derive the generated framing from the
        # source image. The project can still crop to its delivery ratio.
        validate_aspect_ratio = None
    validate_generation_request(
        model, generation_type=capability, duration_seconds=5,
        resolution=body.resolution, aspect_ratio=validate_aspect_ratio,
        has_image_input=(capability == "image_to_video"),
    )
    supported_durations = caps.get("duration_options") or [5]
    inference_units = plan_inference_units(body.target_duration_seconds, supported_durations)
    shot_count = len(inference_units)
    billable_seconds = sum(inference_units)
    # Keep this aligned with the production budget implementation, which
    # rounds each actual scene-generation reservation upward independently.
    per_shot_costs = [provider_cost_usd(model, duration_seconds=seconds) for seconds in inference_units]
    total_provider_cost = sum(per_shot_costs)
    credits = sum(calculate_credits(cost, markup_multiplier=model.get("retail_multiplier")) for cost in per_shot_costs)
    basis = model.get("cost_estimate_basis", "catalog price snapshot; not provider-invoice-reconciled")
    notes = [
        "This is a preflight estimate for visual generation only; final cost is rechecked when the storyboard is approved.",
        "The target runtime is split into the selected model's supported inference durations; clips are trimmed and assembled to the requested timeline.",
    ]
    if capability == "image_to_video" and not caps.get("aspect_ratios"):
        notes.append("The selected model derives native framing from the uploaded image; the final renderer applies the chosen delivery aspect ratio.")
    if caps.get("output_resolution_mode") == "ffmpeg_scale" or body.resolution == "420p":
        notes.append("420p is a final output resize for this route; it does not lower the provider inference charge.")
    if model.get("cost_strategy") == "modal_runtime_estimate":
        notes.append("Modal cost is a runtime/resource estimate, not a reconciled invoice amount.")
    return ProductionEstimateResponse(
        generation_type=capability,
        target_duration_seconds=body.target_duration_seconds,
        model_id=model["id"], model_name=model["name"], provider=model["provider"],
        provider_model_id=model["provider_model_id"], quality_tier=model.get("quality_tier", "standard"),
        resolution=body.resolution, max_shot_duration_seconds=max(supported_durations), shot_count=shot_count,
        scene_count_estimate=(body.target_duration_seconds + 29) // 30,
        billable_generation_seconds=billable_seconds,
        estimated_provider_cost_usd=round(total_provider_cost, 8),
        credits_to_reserve=credits, credit_usd_value=settings.credit_usd_value,
        pricing_strategy=model.get("cost_strategy", "catalog_unit_price"),
        cost_estimate_basis=basis,
        cost_rate_version=settings.modal_cost_rate_version if model["provider"] == "modal" else None,
        capabilities=caps,
        included=["visual generation for planned shots", "clip trimming and assembly estimate"],
        excluded=["voiceover/TTS", "music or sound effects", "licensed stock fees if any", "additional regeneration/retries", "provider charges not represented by the current rate snapshot"],
        note=" ".join(notes),
    )


async def _load_catalog() -> dict:
    return _build_catalog()


@router.post("/estimate", response_model=GenerationEstimateResponse)
async def estimate_generation(
    body: GenerationEstimateRequest,
    _user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(db_session),
):
    """Return a server-authoritative quote without reserving or spending credits.

    The create endpoint repeats capability validation and computes the same
    quote inside the reservation path; the estimate is informational only.
    """
    duration = body.duration_seconds
    if duration is None and body.generation_type in (GenerationType.TEXT_TO_VIDEO, GenerationType.IMAGE_TO_VIDEO):
        duration = 5
    if body.model_id:
        model = get_model(body.model_id)
        if not model.get("enabled", True):
            raise InvalidGenerationParamsError("The selected model is disabled", details={"model_id": body.model_id})
        if model["type"] != body.generation_type:
            raise InvalidGenerationParamsError(
                f"Model {body.model_id} does not support {body.generation_type}",
                details={"model_id": body.model_id, "requested_type": body.generation_type},
            )
        provider_name = "fake" if settings.generation_provider == "fake" else model["provider"]
        if not provider_is_configured(provider_name):
            raise InvalidGenerationParamsError(
                f"Provider '{provider_name}' is not configured",
                details={"model_id": body.model_id, "provider": provider_name, "reason": "provider_not_configured"},
            )
    else:
        chain = await select_with_fallback(session, RoutingRequest(
            capability=body.generation_type,
            quality_mode=body.quality_mode,
            duration_seconds=duration,
        ), max_attempts=1)
        if not chain:
            raise InvalidGenerationParamsError(
                f"No configured model is available for {body.generation_type} at quality '{body.quality_mode}'",
                details={"generation_type": body.generation_type, "quality_mode": body.quality_mode},
            )
        model = chain[0]

    caps = get_capabilities(model)
    resolution = body.resolution
    if resolution is None and body.generation_type in (GenerationType.TEXT_TO_VIDEO, GenerationType.IMAGE_TO_VIDEO):
        supported = caps.get("resolutions", [])
        resolution = "720p" if "720p" in supported else (supported[0] if supported else None)
    aspect_ratio = body.aspect_ratio
    if body.generation_type == GenerationType.IMAGE_TO_VIDEO and not caps.get("aspect_ratios") and body.model_id is None:
        # Auto-routing may land on a model that derives framing from the input;
        # the quote reports that contract rather than failing on a stale UI default.
        aspect_ratio = None
    validate_generation_request(
        model,
        generation_type=body.generation_type,
        duration_seconds=duration,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
    )

    reserve_duration = duration
    if reserve_duration is None and body.generation_type == GenerationType.AVATAR:
        reserve_duration = settings.avatar_reservation_seconds
    elif reserve_duration is None and body.generation_type in (GenerationType.VIDEO_TRANSLATION, GenerationType.AUDIO_REPLACE):
        reserve_duration = settings.unknown_media_reservation_seconds
    safety_margin = 1.5 if body.generation_type == GenerationType.AVATAR else 1.0
    reservation_cost, credits = estimate_reservation(
        model, duration_seconds=reserve_duration, num_images=body.num_images,
        safety_margin=safety_margin,
    )
    provider_cost_estimate = provider_cost_usd(model, duration_seconds=reserve_duration, num_images=body.num_images)
    source = model.get("cost_strategy", "catalog_unit_price")
    basis = model.get("cost_estimate_basis", "catalog provider-price snapshot; not provider-invoice-reconciled")
    notes = []
    if source == "modal_runtime_estimate":
        notes.append("Modal runtime-based estimate using configured resource rates; reconcile against Modal billing reports.")
    else:
        notes.append("Estimate only; provider invoice costs are not currently reported per job.")
    if body.generation_type in (GenerationType.TEXT_TO_VIDEO, GenerationType.IMAGE_TO_VIDEO) and resolution in ("420p", "720p"):
        notes.append("Selected resolution is the final export size. The model may generate at a fixed/native size first; 420p does not reduce the provider's generation charge.")
    if body.duration_seconds is None and body.generation_type == GenerationType.AVATAR:
        notes.append(f"Source duration was unavailable; reservation uses the conservative {settings.avatar_reservation_seconds}s default until the backend verifies the uploaded audio.")
    elif body.duration_seconds is None and body.generation_type in (GenerationType.VIDEO_TRANSLATION, GenerationType.AUDIO_REPLACE):
        notes.append(f"Source duration was unavailable; reservation uses the conservative {settings.unknown_media_reservation_seconds}s default until the backend verifies the uploaded video.")
    return GenerationEstimateResponse(
        generation_type=body.generation_type,
        model_id=model["id"],
        model_name=model["name"],
        provider=model["provider"],
        provider_model_id=model["provider_model_id"],
        quality_tier=model.get("quality_tier", "standard"),
        duration_seconds=duration,
        resolution=resolution,
        estimated_provider_cost_usd=round(provider_cost_estimate, 8),
        estimated_reservation_cost_usd=round(reservation_cost, 8),
        credits_to_reserve=credits,
        credit_usd_value=settings.credit_usd_value,
        pricing_strategy=source,
        cost_estimate_basis=basis,
        cost_rate_version=settings.modal_cost_rate_version if model["provider"] == "modal" else None,
        capabilities=caps,
        note=" ".join(notes),
    )
