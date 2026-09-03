"""Lightweight in-process scheduler using asyncio, wired into the FastAPI
app lifespan (see main.py). For a single-instance deploy this is enough;
if the API ever runs as multiple replicas, move this loop into its own
one-replica process (or use a distributed scheduler / Redis lock) so the
sweep doesn't run N times concurrently."""
import asyncio

from app.core.config import settings
from app.core.logging import get_logger
from app.jobs.cleanup import purge_old_webhook_events
from app.scheduler.tasks import sweep_stuck_generations

logger = get_logger(__name__)


async def run_scheduler_loop(stop_event: asyncio.Event) -> None:
    cleanup_counter = 0
    while not stop_event.is_set():
        try:
            await sweep_stuck_generations()
            cleanup_counter += 1
            if cleanup_counter % 12 == 0:  # roughly once an hour at the default 5-minute interval
                purged = await purge_old_webhook_events()
                if purged:
                    logger.info("webhook_events_purged", count=purged)
        except Exception as exc:  # noqa: BLE001 - the scheduler loop must never die
            logger.error("scheduler_iteration_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.reconciliation_interval_seconds)
        except asyncio.TimeoutError:
            pass
