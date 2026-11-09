"""Thin by design: authenticate -> validate -> call GenerationService ->
return. No pricing math, no fal calls, no DB writes here — see
services/generation/service.py for all of that. Compare this file's size
to the original app/api/generations.py (125 lines doing everything) to see
what "thin router" actually buys you."""
from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GenerationType
from app.dependencies import current_user_id, db_session, require_generations_enabled
from app.schemas.generation import (
    AudioReplaceRequest,
    AvatarRequest,
    GenerationListResponse,
    GenerationResponse,
    ImageToImageRequest,
    ImageToVideoRequest,
    RenameGenerationRequest,
    TextToImageRequest,
    TextToVideoRequest,
    VideoTranslationRequest,
)
from app.services.generation.service import GenerationService

router = APIRouter(prefix="/generations", tags=["generations"])


@router.post("/text-to-image", response_model=GenerationResponse, dependencies=[Depends(require_generations_enabled)])
async def text_to_image(
    body: TextToImageRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return await GenerationService(session).create(
        user_id=user_id, generation_type=GenerationType.TEXT_TO_IMAGE, model_id=body.model, quality_mode=body.quality_mode, prompt=body.prompt,
        aspect_ratio=body.aspect_ratio, num_images=body.num_images, idempotency_key=idempotency_key,
    )


@router.post("/image-to-image", response_model=GenerationResponse, dependencies=[Depends(require_generations_enabled)])
async def image_to_image(
    body: ImageToImageRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return await GenerationService(session).create(
        user_id=user_id, generation_type=GenerationType.IMAGE_TO_IMAGE, model_id=body.model, quality_mode=body.quality_mode, prompt=body.prompt,
        input_s3_key=body.input_s3_key, idempotency_key=idempotency_key,
    )


@router.post("/text-to-video", response_model=GenerationResponse, dependencies=[Depends(require_generations_enabled)])
async def text_to_video(
    body: TextToVideoRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return await GenerationService(session).create(
        user_id=user_id, generation_type=GenerationType.TEXT_TO_VIDEO, model_id=body.model, quality_mode=body.quality_mode, prompt=body.prompt,
        duration_seconds=body.duration_seconds, resolution=body.resolution, aspect_ratio=body.aspect_ratio,
        idempotency_key=idempotency_key,
    )


@router.post("/image-to-video", response_model=GenerationResponse, dependencies=[Depends(require_generations_enabled)])
async def image_to_video(
    body: ImageToVideoRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return await GenerationService(session).create(
        user_id=user_id, generation_type=GenerationType.IMAGE_TO_VIDEO, model_id=body.model, quality_mode=body.quality_mode, prompt=body.prompt,
        input_s3_key=body.input_s3_key, duration_seconds=body.duration_seconds, resolution=body.resolution,
        aspect_ratio=body.aspect_ratio, idempotency_key=idempotency_key,
    )


@router.post("/avatar", response_model=GenerationResponse, dependencies=[Depends(require_generations_enabled)])
async def avatar(
    body: AvatarRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Talking-photo / lip-sync. Duration is unknown until the provider
    processes the audio, so GenerationService reserves against a
    conservative estimate — see pricing.estimate_reservation's
    safety_margin — and the finalize job charges the actual amount."""
    return await GenerationService(session).create(
        user_id=user_id, generation_type=GenerationType.AVATAR, model_id=body.model,
        input_s3_key=body.image_s3_key, secondary_input_s3_key=body.audio_s3_key,
        duration_seconds=body.duration_seconds, reservation_safety_margin=1.5,
        idempotency_key=idempotency_key,
    )


@router.post("/video-translation", response_model=GenerationResponse, dependencies=[Depends(require_generations_enabled)])
async def video_translation(
    body: VideoTranslationRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    model = body.model or ("video-translate-dub" if body.lip_sync else "video-dub-audio-only")
    return await GenerationService(session).create(
        user_id=user_id, generation_type=GenerationType.VIDEO_TRANSLATION, model_id=model,
        input_s3_key=body.video_s3_key, target_language=body.target_language,
        duration_seconds=body.source_duration_seconds, idempotency_key=idempotency_key,
    )


@router.post("/audio-replace", response_model=GenerationResponse, dependencies=[Depends(require_generations_enabled)])
async def audio_replace(
    body: AudioReplaceRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return await GenerationService(session).create(
        user_id=user_id, generation_type=GenerationType.AUDIO_REPLACE, model_id=body.model,
        input_s3_key=body.video_s3_key, secondary_input_s3_key=body.audio_s3_key,
        duration_seconds=body.source_duration_seconds, idempotency_key=idempotency_key,
    )


@router.get("/{generation_id}", response_model=GenerationResponse)
async def get_generation(generation_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    return await GenerationService(session).get_owned(generation_id, user_id)


@router.patch("/{generation_id}", response_model=GenerationResponse)
async def rename_generation(
    generation_id: str, body: RenameGenerationRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)
):
    return await GenerationService(session).rename(generation_id, user_id, body.title)


@router.get("", response_model=GenerationListResponse)
async def list_generations(
    limit: int = 50, offset: int = 0, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)
):
    items = await GenerationService(session).list_for_user(user_id, limit=min(limit, 100), offset=offset)
    return GenerationListResponse(generations=items, limit=limit, offset=offset)


@router.post("/{generation_id}/cancel", response_model=GenerationResponse)
async def cancel_generation(generation_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """gap-closure: previously there was no way to cancel a generation
    anywhere in the API. See GenerationService.cancel."""
    return await GenerationService(session).cancel(generation_id, user_id)
