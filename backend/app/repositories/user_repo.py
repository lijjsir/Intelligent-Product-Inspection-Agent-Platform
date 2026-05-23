from __future__ import annotations

from sqlalchemy import func, or_, select, update
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

    def _apply_filters(self, stmt, org_id: str, keyword: str | None = None, role: str | None = None, is_active: bool | None = None):
        stmt = stmt.where(User.org_id == org_id)

        if keyword:
            pattern = f"%{keyword.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.username).like(pattern),
                    func.lower(User.email).like(pattern),
                )
            )
        if role:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        return stmt

    async def list(
        self,
        org_id: str,
        offset: int,
        limit: int,
        keyword: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> list[User]:
        stmt = self._apply_filters(select(User), org_id, keyword, role, is_active)
        result = await self._session.execute(
            stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def count(
        self,
        org_id: str,
        keyword: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        stmt = self._apply_filters(select(func.count()).select_from(User), org_id, keyword, role, is_active)
        result = await self._session.execute(stmt)
        return int(result.scalar() or 0)

    async def create(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def list_by_org_id(self, org_id: str) -> list[User]:
        result = await self._session.execute(
            select(User).where(User.org_id == org_id).order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def bulk_update_org(self, user_ids: list[str], org_id: str | None) -> int:
        if not user_ids:
            return 0
        result = await self._session.execute(
            update(User)
            .where(User.id.in_(user_ids))
            .values(org_id=org_id)
        )
        await self._session.flush()
        return int(result.rowcount or 0)
