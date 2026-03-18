from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import ToolRegistry


class ToolRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, tool: ToolRegistry) -> ToolRegistry:
        self._session.add(tool)
        await self._session.flush()
        return tool

    async def list_active(self, org_id: str) -> list[ToolRegistry]:
        result = await self._session.execute(
            select(ToolRegistry).where(ToolRegistry.org_id == org_id, ToolRegistry.is_active)
        )
        return list(result.scalars().all())
