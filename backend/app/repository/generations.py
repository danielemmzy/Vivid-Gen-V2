"""All Generation persistence goes through here. Services never import
`sqlalchemy.select` directly for Generation rows — that's the boundary this
layer exists to enforce, so swapping storage engines later only touches
this file."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation import Generation


class GenerationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, generation_id: str) -> Generation | None:
        return await self.session.get(Generation, generation_id)

    async def get_for_update(self, generation_id: str) -> Generation | None:
        stmt = select(Generation).where(Generation.id == generation_id).with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_owned(self, generation_id: str, user_id: str) -> Generation | None:
        stmt = select(Generation).where(Generation.id == generation_id, Generation.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def rename(self, generation_id: str, user_id: str, title: str) -> Generation | None:
        row = await self.get_owned(generation_id, user_id)
        if row:
            row.title = title
        return row

    async def get_by_idempotency_key(self, user_id: str, idempotency_key: str) -> Generation | None:
        stmt = select(Generation).where(
            Generation.user_id == user_id, Generation.idempotency_key == idempotency_key
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_provider_request_id_for_update(self, provider_request_id: str) -> Generation | None:
        stmt = select(Generation).where(Generation.provider_request_id == provider_request_id).with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: str, *, limit: int = 50, offset: int = 0) -> list[Generation]:
        stmt = (
            select(Generation)
            .where(Generation.user_id == user_id)
            .order_by(Generation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_stuck(self, cutoff) -> list[Generation]:
        """Generations that have been non-terminal for longer than `cutoff`
        — the reconciliation scheduler's input query. See scheduler/tasks.py."""
        stmt = select(Generation).where(
            Generation.status.in_(("queued", "processing", "postprocessing")),
            Generation.created_at < cutoff,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_active_for_user(self, user_id: str) -> int:
        stmt = select(Generation).where(
            Generation.user_id == user_id,
            Generation.status.in_(("queued", "reserving_credits", "processing", "postprocessing")),
        )
        return len((await self.session.execute(stmt)).scalars().all())

    def add(self, generation: Generation) -> None:
        self.session.add(generation)
