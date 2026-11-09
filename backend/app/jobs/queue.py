"""Enqueue helper shared by the webhook handler and the movie service.
Kept separate from workers/worker.py so the API process (which enqueues)
doesn't need to import worker startup config."""
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings

_pool = None


async def get_queue():
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def enqueue_generation_submission(generation_id: str) -> None:
    """Durably hand a reserved generation to the worker pool."""
    pool = await get_queue()
    await pool.enqueue_job("submit_generation", generation_id, _expires=3600)


async def enqueue_generation_finalize(generation_id: str) -> None:
    pool = await get_queue()
    await pool.enqueue_job("finalize_generation", generation_id, _expires=3600)


async def enqueue_production_task(job_name: str, task_id: str) -> None:
    """gap-closure (0007): the DAG scheduler's actual dispatch mechanism
    — orchestration/scheduler.py::enqueue_task calls this with whichever
    of the six jobs/production.py job names matches the task's type.
    Replaces `enqueue_movie_assembly` (the old flat "assemble everything"
    trigger, removed this round along with jobs/media.py)."""
    pool = await get_queue()
    await pool.enqueue_job(job_name, task_id, _expires=settings.movie_assembly_max_seconds)
