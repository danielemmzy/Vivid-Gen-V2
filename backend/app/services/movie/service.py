"""Movie/storyboard orchestration — the 'make a movie' feature.

The core problem this solves (per the community research in the
architecture plan): AI video models generate each shot independently, so a
character's face, wardrobe, and the scene's look drift between clips. The
practical workaround creators use manually — lock a character reference
sheet once, and pass it into every shot that character appears in — is
what this service automates:

  1. Create a Character with 1+ reference images (a photo, or a generated
     turnaround sheet). `locked_version` freezes which reference set a shot
     was generated against.
  2. Create a Project with an ordered list of Shots, each shot referencing
     zero or more Characters.
  3. Submitting a shot passes the character's reference image as the
     conditioning image (image-to-video) or as an extra reference input,
     rather than letting the model invent the character fresh each time.
  4. When every shot in a project reaches `completed`, enqueue
     AssembleMovieJob to concatenate them into one final file.

This does not solve character consistency at the model level (that's a
research problem — see NVIDIA's Video Storyboarding paper) — it solves it
at the product level, the same way every competitor mentioned in the
research (ImagineArt, Storyboard Creator AI, invideo) does: pin a
reference, reuse it, let the user regenerate one shot at a time instead of
the whole project when a shot doesn't match.
"""
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GenerationStatus, GenerationType, ProjectStatus, ShotStatus
from app.core.exceptions import (
    CharacterNotFoundError,
    InvalidGenerationParamsError,
    ProjectLimitExceededError,
    ProjectNotFoundError,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.jobs.queue import enqueue_movie_assembly
from app.models.project import Character, Project, Shot
from app.repository.projects import ProjectRepository
from app.services.generation.service import GenerationService
from app.services.providers.fal.catalog import movie_shot_models

logger = get_logger(__name__)


class MovieService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProjectRepository(session)
        self.generations = GenerationService(session)

    async def create_project(self, user_id: str, title: str, description: str | None, aspect_ratio: str, resolution: str) -> Project:
        project = Project(id="proj_" + uuid4().hex, user_id=user_id, title=title, description=description, aspect_ratio=aspect_ratio, resolution=resolution)
        self.repo.add(project)
        await self.session.commit()
        return project

    async def create_character(self, user_id: str, project_id: str, name: str, description: str | None, reference_s3_keys: list[str], voice_id: str | None) -> Character:
        project = await self.repo.get_owned(project_id, user_id)
        if not project:
            raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
        existing_count = await self.repo.count_characters(project_id)
        if existing_count >= settings.max_characters_per_project:
            raise ProjectLimitExceededError(f"Maximum {settings.max_characters_per_project} characters per project")
        character = Character(
            id="char_" + uuid4().hex, user_id=user_id, project_id=project_id, name=name, description=description,
            reference_s3_keys=reference_s3_keys, voice_id=voice_id,
        )
        self.repo.add_character(character)
        await self.session.commit()
        return character

    async def add_shot(
        self, user_id: str, project_id: str, *, prompt: str, camera_notes: str | None, duration_seconds: int,
        character_ids: list[str], model_id: str | None,
    ) -> Shot:
        project = await self.repo.get_owned(project_id, user_id)
        if not project:
            raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
        shots = await self.repo.get_shots(project_id)
        if len(shots) >= settings.max_shots_per_project:
            raise ProjectLimitExceededError(f"Maximum {settings.max_shots_per_project} shots per project")

        for cid in character_ids:
            if not await self.repo.get_character_owned(cid, project_id):
                raise CharacterNotFoundError("Character not found in this project", details={"character_id": cid})

        resolved_model = model_id or (movie_shot_models()[0]["id"] if movie_shot_models() else None)
        if not resolved_model:
            raise InvalidGenerationParamsError("No movie-capable model is available")

        shot = Shot(
            id="shot_" + uuid4().hex, project_id=project_id, order_index=len(shots),
            prompt=prompt, camera_notes=camera_notes, duration_seconds=duration_seconds,
            character_ids=character_ids, model_id=resolved_model,
        )
        self.repo.add_shot(shot)
        await self.session.commit()
        return shot

    async def submit_shot(self, user_id: str, project_id: str, shot_id: str) -> Shot:
        """Submits one shot for generation, conditioning on its first pinned
        character's locked reference image when present — this is the
        continuity mechanism described in the module docstring."""
        shot = await self.repo.get_shot_owned(shot_id, project_id)
        if not shot:
            raise InvalidGenerationParamsError("Shot not found", details={"shot_id": shot_id})

        reference_key = None
        if shot.character_ids:
            character = await self.repo.get_character_owned(shot.character_ids[0], project_id)
            if character and character.reference_s3_keys:
                reference_key = character.reference_s3_keys[0]

        generation_type = GenerationType.IMAGE_TO_VIDEO if reference_key else GenerationType.TEXT_TO_VIDEO
        response = await self.generations.create(
            user_id=user_id, generation_type=generation_type, model_id=shot.model_id, prompt=shot.prompt,
            input_s3_key=reference_key, duration_seconds=shot.duration_seconds, resolution="1080p",
            aspect_ratio="16:9", project_id=project_id, shot_id=shot_id,
            character_id=shot.character_ids[0] if shot.character_ids else None,
        )
        shot.generation_id = response.id
        shot.status = ShotStatus.PROCESSING
        await self.session.commit()
        return shot

    async def maybe_assemble(self, project_id: str) -> None:
        """Called from the GenerationCompleted event handler (see
        events/handlers.py) whenever a shot finishes — checks whether that
        was the last one and, if so, kicks off assembly."""
        shots = await self.repo.get_shots(project_id)
        if shots and all(s.status == ShotStatus.COMPLETED for s in shots):
            project = await self.session.get(Project, project_id)
            if project and project.status != ProjectStatus.READY:
                await enqueue_movie_assembly(project_id)
