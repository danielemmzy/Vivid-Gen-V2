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


async def enqueue_generation_finalize(generation_id: str) -> None:
    pool = await get_queue()
    await pool.enqueue_job("finalize_generation", generation_id, _expires=3600)


async def enqueue_movie_assembly(project_id: str) -> None:
    pool = await get_queue()
    await pool.enqueue_job("assemble_movie", project_id, _expires=settings.movie_assembly_max_seconds)
