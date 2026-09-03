from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_model import AIModel


class AIModelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, model_id: str) -> AIModel | None:
        return await self.session.get(AIModel, model_id)

    async def list_enabled(self) -> list[AIModel]:
        stmt = select(AIModel).where(AIModel.enabled.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())
