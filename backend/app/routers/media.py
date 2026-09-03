from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import current_user_id
from app.services.storage.s3 import presign_download

router = APIRouter(prefix="/media", tags=["media"])


class DownloadRequest(BaseModel):
    key: str = Field(min_length=1, max_length=1024)


@router.post("/presign-download")
async def presign_download_endpoint(req: DownloadRequest, user_id: str = Depends(current_user_id)):
    owned = req.key.startswith(f"generations/{user_id}/") or req.key.startswith(f"uploads/{user_id}/")
    if not owned:
        raise HTTPException(403, "Media key is not owned by this user")
    return {"url": presign_download(req.key)}
