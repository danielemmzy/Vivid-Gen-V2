"""gap-closure: Content Factory (P0.13/P0.14 in the audit's priority list),
revised in 0006 to split what was previously one `Export` row into two
stages, matching the canonical spec's `Master -> ContentVariant -> Export`:

- `ContentVariant`: the actual reframed video for a platform/aspect ratio
  (the rendering work — reused/cached by (project_id, aspect_ratio) so
  requesting the same aspect ratio for two platforms doesn't re-render).
- `Export`: a deliverable record pointing at a variant (or, for
  platform="master", at the original file with no reframe).

Honest scope, unchanged from before: this does NOT generate per-platform
titles, descriptions, or thumbnails (product/prompt-design work, not a
rendering feature) and does NOT do subject-tracking smart crop (see
services/media/ffmpeg.py::reframe_video's docstring).
"""
import tempfile
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import ExportStatus, ProjectStatus
from app.core.exceptions import ProjectNotFoundError, ProjectNotRenderableError
from app.core.logging import get_logger
from app.models.asset import Asset
from app.models.export import ContentVariant, Export
from app.repository.projects import ProjectRepository
from app.services.media.ffmpeg import reframe_video
from app.services.storage.s3 import download_to_path, upload_from_path

logger = get_logger(__name__)


class ExportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.projects = ProjectRepository(session)

    async def _get_or_create_variant(self, user_id: str, project, *, platform: str, aspect_ratio: str) -> ContentVariant:
        """gap-closure (0006): reuses an already-completed variant for
        this (project, aspect_ratio) instead of re-rendering — the same
        9:16 reframe backs both a "tiktok" and an "instagram_reels"
        export, for example, without doing the ffmpeg work twice. A
        variant is keyed on aspect_ratio, not platform, since the
        rendering only depends on aspect ratio; `platform` on the
        returned variant reflects whichever request created it first,
        which is cosmetic only — the Export row (not the variant) is
        what actually records which platform a given deliverable is for."""
        existing = (
            await self.session.execute(
                select(ContentVariant).where(
                    ContentVariant.project_id == project.id,
                    ContentVariant.aspect_ratio == aspect_ratio,
                    ContentVariant.status == ExportStatus.COMPLETED,
                )
            )
        ).scalars().first()
        if existing:
            return existing

        variant = ContentVariant(
            id="cvar_" + uuid4().hex, project_id=project.id, user_id=user_id,
            platform=platform, aspect_ratio=aspect_ratio, status=ExportStatus.PROCESSING,
        )
        self.session.add(variant)
        await self.session.commit()

        try:
            if aspect_ratio == project.aspect_ratio:
                # No reframe needed — the master already matches.
                output_key = project.output_s3_key
            else:
                with tempfile.TemporaryDirectory() as tmpdir:
                    local_master = str(Path(tmpdir) / "master.mp4")
                    download_to_path(project.output_s3_key, local_master)
                    local_out = str(Path(tmpdir) / "variant.mp4")
                    await reframe_video(local_master, local_out, target_aspect_ratio=aspect_ratio)
                    output_key = f"{settings.s3_output_prefix}/{user_id}/projects/{project.id}/variants/{aspect_ratio.replace(':', 'x')}_{uuid4().hex[:8]}.mp4"
                    upload_from_path(local_out, output_key, "video/mp4")

            asset = Asset(
                id="asset_" + uuid4().hex, project_id=project.id, user_id=user_id, type="video", source="render",
                s3_key=output_key, asset_metadata={"kind": "content_variant", "aspect_ratio": aspect_ratio},
            )
            self.session.add(asset)
            await self.session.flush()

            variant.status = ExportStatus.COMPLETED
            variant.s3_key = output_key
            variant.asset_id = asset.id
            await self.session.commit()
            logger.info("content_variant_completed", project_id=project.id, variant_id=variant.id, aspect_ratio=aspect_ratio)
        except Exception as exc:  # noqa: BLE001 - always record the failure, never leave it stuck "processing"
            await self.session.rollback()
            variant = await self.session.get(ContentVariant, variant.id)
            variant.status = ExportStatus.FAILED
            variant.error = str(exc)[:2000]
            await self.session.commit()
            logger.error("content_variant_failed", project_id=project.id, variant_id=variant.id, error=str(exc))

        return variant

    async def create_export(self, user_id: str, project_id: str, *, platform: str, aspect_ratio: str, codec: str = "h264") -> Export:
        project = await self.projects.get_owned(project_id, user_id)
        if not project:
            raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
        if project.status != ProjectStatus.READY or not project.output_s3_key:
            raise ProjectNotRenderableError(
                "This project has no completed master video yet — an export can only be created after the project reaches 'ready'.",
                details={"project_id": project_id, "status": project.status},
            )

        variant = await self._get_or_create_variant(user_id, project, platform=platform, aspect_ratio=aspect_ratio)

        export = Export(
            id="exp_" + uuid4().hex, project_id=project_id, user_id=user_id, variant_id=variant.id,
            platform=platform, aspect_ratio=aspect_ratio, codec=codec,
            status=variant.status, asset_id=variant.asset_id, s3_key=variant.s3_key, error=variant.error,
        )
        self.session.add(export)
        await self.session.commit()
        logger.info("export_created", project_id=project_id, export_id=export.id, variant_id=variant.id, status=export.status)
        return export

    async def list_for_project(self, user_id: str, project_id: str) -> list[Export]:
        project = await self.projects.get_owned(project_id, user_id)
        if not project:
            raise ProjectNotFoundError("Project not found", details={"project_id": project_id})
        rows = (
            await self.session.execute(
                select(Export).where(Export.project_id == project_id).order_by(Export.created_at.desc())
            )
        ).scalars().all()
        return list(rows)
