"""AssembleMovieJob — once every Shot in a Project reaches `completed`,
download each shot's clip in timeline order and concatenate them into the
final movie file. Triggered by services/movie/service.py when the last shot
in a project finishes (checked from the GenerationCompleted event handler,
see events/handlers.py)."""
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.constants import ProjectStatus
from app.core.database import system_session
from app.core.logging import get_logger
from app.models.project import Project, Shot
from app.repository.projects import ProjectRepository
from app.services.media.ffmpeg import FfmpegError, concat_clips
from app.services.storage.s3 import download_to_path, upload_from_path

logger = get_logger(__name__)


async def assemble_movie(ctx, project_id: str) -> None:
    async with system_session() as session:
        repo = ProjectRepository(session)
        project = await session.get(Project, project_id)
        if not project or project.status == ProjectStatus.READY:
            return

        shots = await repo.get_shots(project_id)
        if any(s.status != "completed" for s in shots):
            logger.warning("assemble_movie_called_before_shots_ready", project_id=project_id)
            return

        project.status = ProjectStatus.ASSEMBLING
        await session.commit()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                local_clips: list[str] = []
                for shot in shots:
                    generation = await _get_shot_generation(session, shot)
                    if not generation or not generation.output_s3_key:
                        raise FfmpegError(f"Shot {shot.id} has no completed output")
                    local_path = str(Path(tmpdir) / f"{shot.id}.mp4")
                    download_to_path(generation.output_s3_key, local_path)
                    local_clips.append(local_path)

                output_local = str(Path(tmpdir) / "movie.mp4")
                await concat_clips(local_clips, output_local)

                output_key = f"{settings.s3_output_prefix}/{project.user_id}/projects/{project.id}/movie.mp4"
                upload_from_path(output_local, output_key, "video/mp4")

            project.output_s3_key = output_key
            project.status = ProjectStatus.READY
            project.completed_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("movie_assembled", project_id=project_id, shots=len(shots))
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            project = await session.get(Project, project_id)
            project.status = ProjectStatus.FAILED
            project.error_message = str(exc)[:2000]
            await session.commit()
            logger.error("movie_assembly_failed", project_id=project_id, error=str(exc))


async def _get_shot_generation(session, shot: Shot):
    from app.models.generation import Generation
    if not shot.generation_id:
        return None
    return await session.get(Generation, shot.generation_id)
