from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Character, Project, Shot


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_owned(self, project_id: str, user_id: str) -> Project | None:
        stmt = select(Project).where(Project.id == project_id, Project.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: str, *, limit: int = 50) -> list[Project]:
        stmt = select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_for_user(self, user_id: str) -> int:
        stmt = select(Project).where(Project.user_id == user_id)
        return len((await self.session.execute(stmt)).scalars().all())

    def add(self, project: Project) -> None:
        self.session.add(project)

    async def get_shots(self, project_id: str) -> list[Shot]:
        stmt = select(Shot).where(Shot.project_id == project_id).order_by(Shot.order_index)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_shot_owned(self, shot_id: str, project_id: str) -> Shot | None:
        stmt = select(Shot).where(Shot.id == shot_id, Shot.project_id == project_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def add_shot(self, shot: Shot) -> None:
        self.session.add(shot)

    async def get_character_owned(self, character_id: str, project_id: str) -> Character | None:
        stmt = select(Character).where(Character.id == character_id, Character.project_id == project_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_characters(self, project_id: str) -> list[Character]:
        stmt = select(Character).where(Character.project_id == project_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_characters(self, project_id: str) -> int:
        return len(await self.list_characters(project_id))

    def add_character(self, character: Character) -> None:
        self.session.add(character)
