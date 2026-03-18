from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import ToolRegistry
from app.repositories.tool_repo import ToolRepository


class ToolService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ToolRepository(session)

    async def create_tool(self, payload: dict) -> ToolRegistry:
        tool = ToolRegistry(org_id=self._org_id, **payload)
        return await self._repo.create(tool)

    async def list_active(self) -> list[ToolRegistry]:
        return await self._repo.list_active(self._org_id)
