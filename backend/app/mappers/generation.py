from app.models.generation import Generation
from app.schemas.generation import GenerationResponse
from app.services.storage.s3 import presign_download


def to_response(generation: Generation, *, include_output_url: bool = True) -> GenerationResponse:
    output_url = None
    if include_output_url and generation.output_s3_key:
        output_url = presign_download(generation.output_s3_key)
    return GenerationResponse(
        id=generation.id,
        status=generation.status,
        type=generation.type,
        model_id=generation.model_id,
        duration_seconds=generation.duration_seconds,
        resolution=generation.resolution,
        aspect_ratio=generation.aspect_ratio,
        title=generation.title,
        credits_reserved=generation.credits_reserved,
        credits_charged=generation.credits_charged,
        estimated_provider_cost_usd=float(generation.estimated_provider_cost_usd or 0),
        actual_provider_cost_usd=float(generation.actual_provider_cost_usd) if generation.actual_provider_cost_usd is not None else None,
        actual_cost_source=generation.actual_cost_source,
        retry_count=generation.retry_count,
        output_url=output_url,
        thumbnail_url=presign_download(generation.thumbnail_s3_key) if generation.thumbnail_s3_key else None,
        error_code=generation.error_code,
        error_message=generation.error_message,
        created_at=generation.created_at,
    )
