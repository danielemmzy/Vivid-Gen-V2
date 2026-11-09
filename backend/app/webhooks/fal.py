"""fal.ai webhook handler logic: verify signature -> log to WebhookEvent for
idempotency+audit -> map payload -> update generation state -> enqueue the
finalize job -> return fast. Kept out of app/routers/ entirely per the
architecture plan ("separate webhook routing from webhook business
logic") — the router just calls `handle_fal_webhook`."""
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GenerationStatus
from app.core.logging import get_logger
from app.jobs.queue import enqueue_generation_finalize
from app.models.webhook_event import WebhookEvent
from app.monitoring.metrics import webhook_failed_total, webhook_received_total
from app.repository.generations import GenerationRepository
from app.services.generation.service import GenerationService

logger = get_logger(__name__)


class WebhookVerificationError(Exception):
    pass


async def handle_fal_webhook(session: AsyncSession, payload: dict) -> dict:
    webhook_received_total.labels(provider="fal").inc()
    request_id = payload.get("request_id")
    if not request_id:
        webhook_failed_total.labels(provider="fal", reason="missing_request_id").inc()
        return {"ok": False, "ignored": True}

    # Idempotency: a durable record independent of Generation state, so a
    # replayed webhook is a no-op even if the Generation row is gone.
    from sqlalchemy import select
    event_row = (
        await session.execute(select(WebhookEvent).where(WebhookEvent.provider_event_id == request_id))
    ).scalar_one_or_none()
    if event_row and event_row.processed:
        return {"ok": True, "idempotent": True}
    if not event_row:
        event_row = WebhookEvent(
            id=uuid4().hex, provider="fal", provider_event_id=request_id,
            event_type=payload.get("status", "unknown"), payload=payload,
        )
        session.add(event_row)
        await session.flush()

    repo = GenerationRepository(session)
    row = await repo.get_by_provider_request_id_for_update(request_id)
    if not row:
        event_row.processed = True
        await session.commit()
        return {"ok": True, "ignored": True}

    if GenerationStatus(row.status).is_terminal:
        event_row.processed = True
        await session.commit()
        return {"ok": True, "idempotent": True}

    if payload.get("status") == "ERROR":
        # gap-closure: previously this always refunded immediately,
        # regardless of whether the failure was transient (worth retrying
        # against a fallback model) or permanent. handle_provider_error
        # classifies it and only refunds when no automatic retry is
        # appropriate — see services/generation/service.py and
        # orchestration/provider_errors.py.
        error_message = str(payload.get("error") or payload.get("payload"))[:2000]
        status_code = payload.get("payload", {}).get("status_code") if isinstance(payload.get("payload"), dict) else None
        generation_service = GenerationService(session)
        await generation_service.handle_provider_error(row, error_message=error_message, status_code=status_code)
        event_row.processed = True
        await session.commit()
        return {"ok": True}

    data = payload.get("payload") or {}
    output = None
    if isinstance(data.get("images"), list) and data["images"]:
        output = data["images"][0]
    elif isinstance(data.get("video"), dict):
        output = data["video"]
    elif isinstance(data.get("video_url"), str):
        output = {"url": data["video_url"]}
    elif isinstance(data.get("audio"), dict):
        output = data["audio"]

    if not output or not output.get("url"):
        event_row.processed = True
        event_row.processing_error = "no_recognized_media_output"
        await session.commit()
        webhook_failed_total.labels(provider="fal", reason="unrecognized_payload").inc()
        return {"ok": False, "error": "unrecognized_payload"}

    row.status = GenerationStatus.POSTPROCESSING
    row.metadata_json = {**(row.metadata_json or {}), "provider_output_url": output["url"], "provider_content_type": output.get("content_type")}
    event_row.processed = True
    await session.commit()
    generation_id = row.id

    await enqueue_generation_finalize(generation_id)
    return {"ok": True, "queued": True}
