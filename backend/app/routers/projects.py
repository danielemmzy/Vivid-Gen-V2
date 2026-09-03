"""The movie/storyboard feature's API surface: create a project, add
characters (reference sheets for identity consistency), add shots, submit
shots for generation, and check assembly status. See
services/movie/service.py for the orchestration this delegates to."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import current_user_id, db_session
from app.services.movie.service import MovieService
from app.services.storage.s3 import presign_download

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"


class CreateCharacterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    reference_s3_keys: list[str] = Field(min_length=1, max_length=6)
    voice_id: str | None = None


class AddShotRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    camera_notes: str | None = Field(default=None, max_length=500)
    duration_seconds: int = Field(default=5, ge=3, le=15)
    character_ids: list[str] = Field(default_factory=list, max_length=4)
    model_id: str | None = None


def _project_dict(project) -> dict:
    return {
        "id": project.id, "title": project.title, "description": project.description, "status": project.status,
        "aspect_ratio": project.aspect_ratio, "resolution": project.resolution,
        "output_url": presign_download(project.output_s3_key) if project.output_s3_key else None,
        "error_message": project.error_message,
    }


def _shot_dict(shot) -> dict:
    return {
        "id": shot.id, "order_index": shot.order_index, "status": shot.status, "prompt": shot.prompt,
        "camera_notes": shot.camera_notes, "duration_seconds": shot.duration_seconds,
        "character_ids": shot.character_ids, "generation_id": shot.generation_id,
    }


@router.post("")
async def create_project(body: CreateProjectRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    project = await MovieService(session).create_project(user_id, body.title, body.description, body.aspect_ratio, body.resolution)
    return _project_dict(project)


@router.post("/{project_id}/characters")
async def create_character(project_id: str, body: CreateCharacterRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    character = await MovieService(session).create_character(user_id, project_id, body.name, body.description, body.reference_s3_keys, body.voice_id)
    return {"id": character.id, "name": character.name, "locked_version": character.locked_version, "reference_s3_keys": character.reference_s3_keys}


@router.post("/{project_id}/shots")
async def add_shot(project_id: str, body: AddShotRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    shot = await MovieService(session).add_shot(
        user_id, project_id, prompt=body.prompt, camera_notes=body.camera_notes,
        duration_seconds=body.duration_seconds, character_ids=body.character_ids, model_id=body.model_id,
    )
    return _shot_dict(shot)


@router.post("/{project_id}/shots/{shot_id}/submit")
async def submit_shot(project_id: str, shot_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    shot = await MovieService(session).submit_shot(user_id, project_id, shot_id)
    return _shot_dict(shot)


@router.get("/{project_id}")
async def get_project(project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    repo_service = MovieService(session)
    project = await repo_service.repo.get_owned(project_id, user_id)
    if not project:
        from app.core.exceptions import ProjectNotFoundError
        raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
    shots = await repo_service.repo.get_shots(project_id)
    return {**_project_dict(project), "shots": [_shot_dict(s) for s in shots]}


@router.get("")
async def list_projects(user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    projects = await MovieService(session).repo.list_for_user(user_id)
    return {"projects": [_project_dict(p) for p in projects]}
