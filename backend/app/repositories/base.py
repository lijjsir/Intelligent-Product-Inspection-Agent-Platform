from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, model: Any, id_: Any) -> T | None:
        result = await self._session.execute(select(model).where(model.id == id_))
        return result.scalar_one_or_none()

    async def create(self, instance: T) -> T:
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def list_paged(self, model: Any, page: int, size: int):
        stmt = select(model).offset((page - 1) * size).limit(size)
        result = await self._session.execute(stmt)
        return result.scalars().all()
