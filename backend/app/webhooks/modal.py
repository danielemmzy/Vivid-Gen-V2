"""Modal webhook handler logic — mirrors app/webhooks/fal.py's structure
(verify -> dedup via WebhookEvent -> update Generation -> enqueue finalize)
exactly, because the rest of the generation lifecycle (finalize job,
credit charge, frontend polling) must not care which provider produced a
completion. The one real difference: we define this payload shape
ourselves (see modal_app/wan_worker.py, the code that sends it), so it's
simpler than fal's — no nested "images"/"video"/"audio" shape-sniffing.

Expected payload:
{
  "call_id": "<modal FunctionCall id — matches ProviderSubmission.provider_request_id>",
  "status": "completed" | "failed",
  "output_url": "<presigned or public URL to the generated file>",   # completed only
  "error": "<message>",                                              # failed only
  "runtime_seconds": 12.4, "model_load_seconds": 8.1, "inference_seconds": 4.3  # runtime is not GPU-only time
}
"""
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GenerationStatus
from app.core.config import settings
from app.core.logging import get_logger
from app.jobs.queue import enqueue_generation_finalize
from app.models.webhook_event import WebhookEvent
from app.monitoring.metrics import webhook_failed_total, webhook_received_total
from app.repository.generations import GenerationRepository
from app.services.generation.service import GenerationService

logger = get_logger(__name__)


async def handle_modal_webhook(session: AsyncSession, payload: dict) -> dict:
    webhook_received_total.labels(provider="modal").inc()
    call_id = payload.get("call_id")
    if not call_id:
        webhook_failed_total.labels(provider="modal", reason="missing_call_id").inc()
        return {"ok": False, "ignored": True}

    event_row = (
        await session.execute(select(WebhookEvent).where(WebhookEvent.provider_event_id == call_id))
    ).scalar_one_or_none()
    if event_row and event_row.processed:
        return {"ok": True, "idempotent": True}
    if not event_row:
        event_row = WebhookEvent(
            id=uuid4().hex, provider="modal", provider_event_id=call_id,
            event_type=payload.get("status", "unknown"), payload=payload,
        )
        session.add(event_row)
        await session.flush()

    repo = GenerationRepository(session)
    row = await repo.get_by_provider_request_id_for_update(call_id)
    if not row:
        event_row.processed = True
        await session.commit()
        return {"ok": True, "ignored": True}

    if GenerationStatus(row.status).is_terminal:
        event_row.processed = True
        await session.commit()
        return {"ok": True, "idempotent": True}

    runtime_seconds = payload.get("runtime_seconds")
    # Backward compatibility for callbacks emitted by the pre-fix worker.
    # Old `gpu_seconds` actually contained total wall runtime; preserve it but
    # explicitly label the resulting cost as an estimate, not GPU telemetry.
    if runtime_seconds is None:
        runtime_seconds = payload.get("gpu_seconds")
    cost_breakdown = {
        k: payload[k] for k in ("runtime_seconds", "gpu_seconds", "model_load_seconds", "inference_seconds") if k in payload
    }
    if runtime_seconds is not None:
        from app.services.generation.pricing import modal_runtime_cost_usd
        cost_breakdown["provider_runtime_cost_estimate_usd"] = round(modal_runtime_cost_usd(float(runtime_seconds)), 8)
        cost_breakdown["provider_cost_source"] = "modal_runtime_estimate"
        cost_breakdown["modal_cost_rate_version"] = settings.modal_cost_rate_version

    if payload.get("status") == "failed":
        # gap-closure: previously always refunded immediately, same issue
        # as webhooks/fal.py before this pass — now goes through the same
        # transient/permanent classification + fallback-resubmit logic.
        row.metadata_json = {**(row.metadata_json or {}), **cost_breakdown}
        error_message = str(payload.get("error"))[:2000]
        generation_service = GenerationService(session)
        await generation_service.handle_provider_error(row, error_message=error_message)
        event_row.processed = True
        await session.commit()
        return {"ok": True}

    output_url = payload.get("output_url")
    if not output_url:
        row.metadata_json = {**(row.metadata_json or {}), **cost_breakdown}
        event_row.processed = True
        event_row.processing_error = "no_output_url"
        await GenerationService(session).handle_provider_error(
            row, error_message="Modal callback completed without an output_url", status_code=502,
        )
        await session.commit()
        webhook_failed_total.labels(provider="modal", reason="missing_output_url").inc()
        return {"ok": False, "error": "missing_output_url"}

    row.status = GenerationStatus.POSTPROCESSING
    row.metadata_json = {**(row.metadata_json or {}), "provider_output_url": output_url, **cost_breakdown}
    event_row.processed = True
    await session.commit()
    generation_id = row.id

    await enqueue_generation_finalize(generation_id)
    return {"ok": True, "queued": True}
