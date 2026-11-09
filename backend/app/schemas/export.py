from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# Kept small and concrete rather than `str` — see routers/exports.py. Adding
# a platform later just means adding a literal + (if it implies a specific
# aspect ratio) a frontend preset; it does not touch the render path, which
# only ever cares about aspect_ratio.
ExportPlatform = Literal["youtube", "tiktok", "instagram_reels", "instagram_feed", "facebook", "master"]
ExportAspectRatio = Literal["16:9", "9:16", "1:1", "4:5"]


class CreateExportRequest(BaseModel):
    platform: ExportPlatform
    aspect_ratio: ExportAspectRatio
    codec: str = "h264"  # gap-closure (0006): Export.codec — see models/export.py


class ExportResponse(BaseModel):
    id: str
    project_id: str
    variant_id: str | None = None
    platform: str
    aspect_ratio: str
    codec: str = "h264"
    status: str
    error: str | None = None
    download_url: str | None = None
    created_at: datetime | None = None


class ExportListResponse(BaseModel):
    exports: list[ExportResponse]
