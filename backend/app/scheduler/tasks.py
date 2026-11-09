"""The reconciliation sweep — the production safety net that did not exist
anywhere in the original codebase. If a fal.ai webhook is ever dropped
(network blip, our endpoint briefly down during a deploy, fal-side retry
exhaustion) or a worker crashes mid-finalize, a generation can get stuck
with its credits reserved and no way for the user to know. This task
finds anything stuck past `stuck_generation_minutes` and repairs it.

Two distinct stuck cases, handled differently — this split was added
after designing tests/integration/test_worker_crash_reconciliation.py
(chaos Test 5) and finding the original single-path version couldn't
actually recover the most common crash scenario:

  * status == POSTPROCESSING: the webhook already told us the provider
    finished (the output URL is sitting in metadata_json) — a stuck row
    here means the finalize *worker* crashed or the process restarted
    before the job ran to completion, not that the provider is slow.
    Recovery is just re-enqueueing the finalize job; provider-agnostic,
    works identically under `fal` or `fake`. This used to be entirely
    unreachable when GENERATION_PROVIDER != "fal" — the whole sweep
    short-circuited to a no-op in fake/dev mode, which meant the exact
    scenario Test 5 exists to validate couldn't be exercised without
    real fal.ai spend. Fixed.

  * status in (QUEUED, PROCESSING): no completion signal has arrived yet.
    Under `fal`, poll the provider's own status API. Under `fake`, there
    is no such API — and the fake provider's self-completion is an
    in-memory `asyncio.create_task`, which does NOT survive an API
    process restart. A generation stuck here in fake mode genuinely has
    no way to know if it finished, so the conservative, correct move is
    the same one a real "provider silently dropped this job" case gets:
    refund and fail it.
"""
from datetime import datetime, timedelta, timezone

import fal_client

from app.core.config import settings
from app.core.constants import GenerationStatus
from app.core.database import system_session
from app.core.logging import get_logger
from app.jobs.queue import enqueue_generation_finalize, enqueue_generation_submission
from app.repository.generations import GenerationRepository
from app.services.credits.service import CreditService

logger = get_logger(__name__)


async def sweep_stuck_generations() -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.stuck_generation_minutes)
    recovered = repaired = 0

    async with system_session() as session:
        repo = GenerationRepository(session)
        stuck = await repo.list_stuck(cutoff)

        for row in stuck:
            if row.status == GenerationStatus.POSTPROCESSING:
                await enqueue_generation_finalize(row.id)
                recovered += 1
                logger.info("reconciliation_reenqueued_finalize", generation_id=row.id)
                continue

            if not row.provider_request_id:
                # A QUEUED generation may have survived an API crash between
                # the DB commit and Redis enqueue. Re-enqueue it instead of
                # refunding: ARQ is the durable hand-off, and this sweep is
                # the second line of defense.
                if row.status == GenerationStatus.QUEUED:
                    await enqueue_generation_submission(row.id)
                    recovered += 1
                    logger.info("reconciliation_reenqueued_submission", generation_id=row.id)
                    continue
                # RESERVING_CREDITS without a provider id is a genuinely
                # abandoned reservation.
                await _refund_and_fail(session, row.id, row.user_id, row.credits_reserved, "STUCK_NO_PROVIDER_ID")
                repaired += 1
                continue

            if settings.generation_provider != "fal":
                await _refund_and_fail(session, row.id, row.user_id, row.credits_reserved, "STUCK_FAKE_PROVIDER_NO_SIGNAL")
                repaired += 1
                continue

            try:
                status = fal_client.status(row.provider_request_id, with_logs=False)
            except Exception as exc:  # noqa: BLE001 - treat an unreachable provider as unresolved this pass
                logger.warning("reconciliation_status_check_failed", generation_id=row.id, error=str(exc))
                continue

            status_name = getattr(status, "status", None) or (status.get("status") if isinstance(status, dict) else None)
            if status_name == "COMPLETED":
                await enqueue_generation_finalize(row.id)
                recovered += 1
            elif status_name in ("ERROR", "CANCELLED"):
                await _refund_and_fail(session, row.id, row.user_id, row.credits_reserved, "STUCK_PROVIDER_FAILED")
                repaired += 1
            # else still legitimately in progress on fal's side — leave it

    logger.info("reconciliation_sweep_complete", stuck=len(stuck), recovered=recovered, repaired=repaired)
    return {"stuck": len(stuck), "recovered": recovered, "repaired": repaired}


async def _refund_and_fail(session, generation_id: str, user_id: str, credits: int, error_code: str) -> None:
    repo = GenerationRepository(session)
    row = await repo.get_for_update(generation_id)
    if not row or row.status in (GenerationStatus.COMPLETED, GenerationStatus.REFUNDED, GenerationStatus.FAILED):
        return
    credit_service = CreditService(session)
    await credit_service.refund(user_id, generation_id, credits, f"Reconciliation refund: {error_code}")
    row.status = GenerationStatus.REFUNDED
    row.error_code = error_code
    row.failed_at = datetime.now(timezone.utc)
    await session.commit()
