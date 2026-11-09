"""V2 Phase 11, completed: BrandKit CRUD. Applying a brand kit to a video
happens in orchestration/render_manifest_builder.py, not here; this
router only manages the brand kit records themselves.

gap-closure: intro_asset_id/outro_asset_id existed on the BrandKit model
since migration 0003 but were never accepted by Create/Update — a user
could store an intro/outro clip reference only by editing the DB row
directly. Added to both request schemas below. A DELETE endpoint was
also simply missing.
"""
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VividGenError
from app.dependencies import current_user_id, db_session
from app.models.brand_kit import BrandKit
from app.repository.brand_kits import BrandKitRepository
from app.services.storage.s3 import presign_download

router = APIRouter(prefix="/brand-kits", tags=["brand-kits"])


class BrandKitNotFoundError(VividGenError):
    http_status = 404
    code = "BRAND_KIT_NOT_FOUND"


class CreateBrandKitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    logo_s3_key: str | None = None
    watermark_s3_key: str | None = None
    default_music_s3_key: str | None = None
    primary_color: str | None = Field(default=None, max_length=16)
    secondary_color: str | None = Field(default=None, max_length=16)
    font_family: str | None = Field(default=None, max_length=120)
    caption_style: str = "minimal"
    cta_text: str | None = Field(default=None, max_length=200)
    voice_id: str | None = None
    intro_asset_id: str | None = None
    outro_asset_id: str | None = None


class UpdateBrandKitRequest(BaseModel):
    name: str | None = None
    logo_s3_key: str | None = None
    watermark_s3_key: str | None = None
    default_music_s3_key: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    font_family: str | None = None
    caption_style: str | None = None
    cta_text: str | None = None
    voice_id: str | None = None
    intro_asset_id: str | None = None
    outro_asset_id: str | None = None


def _dict(kit: BrandKit) -> dict:
    return {
        "id": kit.id, "name": kit.name,
        "logo_url": presign_download(kit.logo_s3_key) if kit.logo_s3_key else None,
        "watermark_url": presign_download(kit.watermark_s3_key) if kit.watermark_s3_key else None,
        "default_music_url": presign_download(kit.default_music_s3_key) if kit.default_music_s3_key else None,
        "primary_color": kit.primary_color, "secondary_color": kit.secondary_color,
        "font_family": kit.font_family, "caption_style": kit.caption_style,
        "cta_text": kit.cta_text, "voice_id": kit.voice_id,
        "intro_asset_id": kit.intro_asset_id, "outro_asset_id": kit.outro_asset_id,
    }


@router.post("")
async def create_brand_kit(body: CreateBrandKitRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    kit = BrandKit(id="brand_" + uuid4().hex, user_id=user_id, **body.model_dump())
    BrandKitRepository(session).add(kit)
    await session.commit()
    return _dict(kit)


@router.get("")
async def list_brand_kits(user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    kits = await BrandKitRepository(session).list_for_user(user_id)
    return {"brand_kits": [_dict(k) for k in kits]}


@router.get("/{brand_kit_id}")
async def get_brand_kit(brand_kit_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    kit = await BrandKitRepository(session).get_owned(brand_kit_id, user_id)
    if not kit:
        raise BrandKitNotFoundError("Brand kit not found", details={"brand_kit_id": brand_kit_id})
    return _dict(kit)


@router.patch("/{brand_kit_id}")
async def update_brand_kit(brand_kit_id: str, body: UpdateBrandKitRequest, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    kit = await BrandKitRepository(session).get_owned(brand_kit_id, user_id)
    if not kit:
        raise BrandKitNotFoundError("Brand kit not found", details={"brand_kit_id": brand_kit_id})
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(kit, field, value)
    await session.commit()
    return _dict(kit)


@router.delete("/{brand_kit_id}")
async def delete_brand_kit(brand_kit_id: str, user_id: str = Depends(current_user_id), session: AsyncSession = Depends(db_session)):
    """gap-closure: previously there was no way to delete a brand kit
    through the API at all."""
    kit = await BrandKitRepository(session).get_owned(brand_kit_id, user_id)
    if not kit:
        raise BrandKitNotFoundError("Brand kit not found", details={"brand_kit_id": brand_kit_id})
    await session.delete(kit)
    await session.commit()
    return {"deleted": True, "brand_kit_id": brand_kit_id}
