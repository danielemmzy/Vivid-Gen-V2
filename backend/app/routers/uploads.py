"""gap-closure: upload content-type hardening. Previously POST
/uploads/presign accepted a client-declared content_type/extension with
no server-side allowlist — a presigned PUT was issued for literally any
content_type the caller sent, and that key later gets handed straight to
a generation provider as an input asset (services/generation/service.py).
This does not add post-upload magic-byte verification (that would need
the backend to intercept the actual upload, which currently goes
client -> S3 directly via the presigned URL, not through this API) — it
closes the cheaper, still-real half of the gap: a client can no longer
even obtain a presigned URL for a disallowed content_type."""
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.exceptions import UnsupportedUploadTypeError
from app.dependencies import current_user_id
from app.services.storage.s3 import presign_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])

# Maps an allowed content_type to the extension we'll force the S3 key to
# use, regardless of what the client sent as file_name — this also closes
# the "client controls the extension too" half of the original gap (a
# client could otherwise request content_type=image/png with a .exe
# filename).
_EXTENSION_FOR_CONTENT_TYPE = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
    "video/x-matroska": ".mkv", "video/x-msvideo": ".avi",
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/aac": ".aac", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a", "audio/ogg": ".ogg",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}


class PresignRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="media", pattern=r"^[a-zA-Z0-9_-]{1,191}$")


@router.post("/presign")
async def presign(req: PresignRequest, user_id: str = Depends(current_user_id)):
    if req.content_type not in settings.allowed_upload_content_types:
        raise UnsupportedUploadTypeError(
            f"content_type '{req.content_type}' is not accepted for uploads",
            details={"content_type": req.content_type, "allowed": settings.allowed_upload_content_types},
        )
    ext = _EXTENSION_FOR_CONTENT_TYPE.get(req.content_type, Path(req.file_name).suffix or ".bin")
    url, key = presign_upload(req.content_type, ext, f"{user_id}/{req.purpose}")
    return {"url": url, "key": key}
