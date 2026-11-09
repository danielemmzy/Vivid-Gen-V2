"""V2 Phase 22 (spec §51-§52): Repurpose / Content Factory, first slice.

Reuses workflows/shorts.py's exact pipeline against an already-completed
Project's assembled output (`Project.output_s3_key`) instead of a fresh
upload — "one source -> many outputs" from spec §51, implemented as
"the source is a Project you already made" rather than a new concept.

NOT implemented: the full Content Factory fan-out (spec §52 — YouTube +
Shorts + Reels + TikTok + Ads + thumbnails + titles + descriptions all
from one idea). This is the Shorts slice only, since that's the one
piece with a complete real pipeline (transcribe -> highlight-detect ->
trim) built this session. Reels/TikTok would reuse this unchanged (same
9:16 crop); a distinct Ads-from-existing-footage repurpose and
thumbnail/title/description generation are separate, unbuilt work.
"""
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VividGenError
from app.models.project import Project
from app.workflows.shorts import ShortsRequest, generate_shorts


class RepurposeRequest(BaseModel):
    max_clips: int = Field(default=5, ge=1, le=10)


class ProjectNotReadyError(VividGenError):
    http_status = 409
    code = "PROJECT_NOT_READY"


async def repurpose_as_shorts(session: AsyncSession, user_id: str, project: Project, body: RepurposeRequest):
    if not project.output_s3_key:
        raise ProjectNotReadyError("This project has no completed output to repurpose yet")
    return await generate_shorts(session, user_id, project.id, ShortsRequest(source_video_s3_key=project.output_s3_key, max_clips=body.max_clips))
