"""gap-closure: Content Factory / Export domain (previously zero lines of
code — see services/export/service.py for scope notes). Nested under
/projects/{project_id}/exports since an export always belongs to exactly
one project's master."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import current_user_id, db_session
from app.mappers.export import to_export_response
from app.schemas.export import CreateExportRequest, ExportListResponse, ExportResponse
from app.services.export.service import ExportService

router = APIRouter(prefix="/projects/{project_id}/exports", tags=["exports"])


@router.post("", response_model=ExportResponse)
async def create_export(
    project_id: str, body: CreateExportRequest,
    user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session),
):
    export = await ExportService(session).create_export(
        user_id, project_id, platform=body.platform, aspect_ratio=body.aspect_ratio, codec=body.codec,
    )
    return to_export_response(export)


@router.get("", response_model=ExportListResponse)
async def list_exports(project_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    exports = await ExportService(session).list_for_project(user_id, project_id)
    return ExportListResponse(exports=[to_export_response(e) for e in exports])
