from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.dependencies import current_user_id
from app.services.storage.s3 import presign_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])


class PresignRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="media", pattern=r"^[a-zA-Z0-9_-]{1,32}$")


@router.post("/presign")
async def presign(req: PresignRequest, user_id: str = Depends(current_user_id)):
    ext = Path(req.file_name).suffix or ".bin"
    url, key = presign_upload(req.content_type, ext, f"{user_id}/{req.purpose}")
    return {"url": url, "key": key}
