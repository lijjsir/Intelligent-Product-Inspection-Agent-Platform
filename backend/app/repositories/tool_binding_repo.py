from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import AgentToolBinding


class ToolBindingRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, binding: AgentToolBinding) -> AgentToolBinding:
        self._session.add(binding)
        await self._session.flush()
        await self._session.refresh(binding)
        return binding

    async def list_all(self, org_id: str) -> list[AgentToolBinding]:
        result = await self._session.execute(
            select(AgentToolBinding)
            .where(AgentToolBinding.org_id == org_id)
            .order_by(AgentToolBinding.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_tool(self, org_id: str, tool_id: str) -> list[AgentToolBinding]:
        result = await self._session.execute(
            select(AgentToolBinding)
            .where(AgentToolBinding.org_id == org_id, AgentToolBinding.tool_id == tool_id)
            .order_by(AgentToolBinding.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_agent(self, org_id: str, agent_id: str) -> list[AgentToolBinding]:
        result = await self._session.execute(
            select(AgentToolBinding)
            .where(
                AgentToolBinding.org_id == org_id,
                AgentToolBinding.agent_id == agent_id,
                AgentToolBinding.binding_status == "active",
            )
            .order_by(AgentToolBinding.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, binding_id: str) -> AgentToolBinding | None:
        result = await self._session.execute(
            select(AgentToolBinding).where(
                AgentToolBinding.id == binding_id,
                AgentToolBinding.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_agent_and_tool(
        self, org_id: str, agent_id: str, tool_id: str
    ) -> AgentToolBinding | None:
        result = await self._session.execute(
            select(AgentToolBinding).where(
                AgentToolBinding.org_id == org_id,
                AgentToolBinding.agent_id == agent_id,
                AgentToolBinding.tool_id == tool_id,
            )
        )
        return result.scalar_one_or_none()

    async def save(self, binding: AgentToolBinding, updates: dict) -> AgentToolBinding:
        for key, value in updates.items():
            setattr(binding, key, value)
        await self._session.flush()
        await self._session.refresh(binding)
        return binding

    async def delete(self, binding: AgentToolBinding) -> None:
        await self._session.delete(binding)
        await self._session.flush()
