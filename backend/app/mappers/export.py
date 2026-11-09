from app.models.export import Export
from app.schemas.export import ExportResponse
from app.services.storage.s3 import presign_download


def to_export_response(export: Export) -> ExportResponse:
    return ExportResponse(
        id=export.id, project_id=export.project_id, variant_id=export.variant_id,
        platform=export.platform, aspect_ratio=export.aspect_ratio, codec=export.codec,
        status=export.status, error=export.error,
        download_url=presign_download(export.s3_key) if export.s3_key else None,
        created_at=export.created_at,
    )
