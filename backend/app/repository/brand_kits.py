from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_kit import BrandKit


class BrandKitRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_owned(self, brand_kit_id: str, user_id: str) -> BrandKit | None:
        stmt = select(BrandKit).where(BrandKit.id == brand_kit_id, BrandKit.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: str) -> list[BrandKit]:
        stmt = select(BrandKit).where(BrandKit.user_id == user_id).order_by(BrandKit.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    def add(self, brand_kit: BrandKit) -> None:
        self.session.add(brand_kit)
