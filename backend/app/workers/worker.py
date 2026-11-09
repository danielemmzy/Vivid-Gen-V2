"""ARQ worker configuration — the 'how' (concurrency, retries, timeouts).
What each job actually does lives in app/jobs/, not here — see the
architecture plan's jobs-vs-workers split. Run with:
    python -m app.workers.worker
Scale horizontally by running more replicas of this process; ARQ fans work
out across them via the shared Redis queue automatically.
"""
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.logging import configure_logging
from app.jobs.generation import finalize_generation, submit_generation
from app.jobs.production import (
    run_branding_task,
    run_captions_task,
    run_music_task,
    run_render_task,
    run_scene_task,
    run_voice_task,
)
from app.monitoring.sentry import init_sentry


async def _startup(ctx):
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    init_sentry()


class WorkerSettings:
    # gap-closure (0007): `assemble_movie` (the old flat "last shot done
    # -> assemble everything in one job" trigger) is gone — replaced by
    # six per-task-type jobs the DAG scheduler (orchestration/
    # scheduler.py) dispatches to individually. See jobs/production.py.
    functions = [
        submit_generation, finalize_generation, run_scene_task, run_voice_task, run_captions_task,
        run_music_task, run_branding_task, run_render_task,
    ]
    on_startup = _startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = max(300, settings.movie_assembly_max_seconds)
    keep_result = 3600
    health_check_interval = 30
    max_tries = 3
    retry_jobs = True


if __name__ == "__main__":
    from arq import run_worker
    run_worker(WorkerSettings)
