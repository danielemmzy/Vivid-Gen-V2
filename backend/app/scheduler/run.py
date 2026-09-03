"""Standalone scheduler process — run with `python -m app.scheduler.run`.
No longer runs inside the FastAPI app's lifespan (see leader.py's
docstring for why: multiple API replicas would each run their own
reconciliation sweep). Run exactly one replica of this in production; if
you do run more than one for redundancy, leader.py's Redis lock ensures
only one is ever active at a time."""
import asyncio

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.scheduler.leader import run_as_leader_or_wait
from app.scheduler.scheduler import run_scheduler_loop

configure_logging(level=settings.log_level, json_output=settings.log_json)
logger = get_logger(__name__)


async def main() -> None:
    stop_event = asyncio.Event()
    while not stop_event.is_set():
        is_leader = await run_as_leader_or_wait(stop_event)
        if is_leader:
            await run_scheduler_loop(stop_event)
            break
        logger.info("scheduler_standby", message="another replica holds the leader lock")
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
