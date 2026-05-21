from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import ToolVersion


class ToolVersionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, version: ToolVersion) -> ToolVersion:
        self._session.add(version)
        await self._session.flush()
        await self._session.refresh(version)
        return version

    async def list_by_tool(self, org_id: str, tool_id: str) -> list[ToolVersion]:
        result = await self._session.execute(
            select(ToolVersion)
            .where(ToolVersion.org_id == org_id, ToolVersion.tool_id == tool_id)
            .order_by(ToolVersion.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, version_id: str) -> ToolVersion | None:
        result = await self._session.execute(
            select(ToolVersion).where(
                ToolVersion.id == version_id,
                ToolVersion.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_tool_and_version(
        self, org_id: str, tool_id: str, version: str
    ) -> ToolVersion | None:
        result = await self._session.execute(
            select(ToolVersion).where(
                ToolVersion.org_id == org_id,
                ToolVersion.tool_id == tool_id,
                ToolVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def save(self, version: ToolVersion, updates: dict) -> ToolVersion:
        for key, value in updates.items():
            setattr(version, key, value)
        await self._session.flush()
        await self._session.refresh(version)
        return version
