from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_username(self, org_id: str, username: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.org_id == org_id, User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, org_id: str, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.org_id == org_id, User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, org_id: str, user_id: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.org_id == org_id, User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def list(self, org_id: str, offset: int, limit: int) -> list[User]:
        result = await self._session.execute(
            select(User)
            .where(User.org_id == org_id)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count(self, org_id: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(User).where(User.org_id == org_id)
        )
        return int(result.scalar() or 0)

    async def create(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user
