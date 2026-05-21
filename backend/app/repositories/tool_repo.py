from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import ToolDefinition, ToolExecution


class ToolRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, tool: ToolDefinition) -> ToolDefinition:
        self._session.add(tool)
        await self._session.flush()
        await self._session.refresh(tool)
        return tool

    async def list_active(self, org_id: str) -> list[ToolDefinition]:
        result = await self._session.execute(
            select(ToolDefinition)
            .where(
                or_(ToolDefinition.org_id == org_id, ToolDefinition.org_id.is_(None)),
                ToolDefinition.status == "active",
                ToolDefinition.deleted_at.is_(None),
            )
            .order_by(ToolDefinition.updated_at.desc(), ToolDefinition.display_name.asc()),
        )
        return list(result.scalars().all())

    async def list_all(self, org_id: str) -> list[ToolDefinition]:
        result = await self._session.execute(
            select(ToolDefinition)
            .where(
                or_(ToolDefinition.org_id == org_id, ToolDefinition.org_id.is_(None)),
                ToolDefinition.deleted_at.is_(None),
            )
            .order_by(ToolDefinition.updated_at.desc(), ToolDefinition.display_name.asc()),
        )
        return list(result.scalars().all())

    async def get(self, org_id: str, tool_id: str) -> ToolDefinition | None:
        result = await self._session.execute(
            select(ToolDefinition).where(
                ToolDefinition.id == tool_id,
                or_(ToolDefinition.org_id == org_id, ToolDefinition.org_id.is_(None)),
                ToolDefinition.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_tool_key(self, org_id: str, tool_key: str) -> ToolDefinition | None:
        result = await self._session.execute(
            select(ToolDefinition).where(
                ToolDefinition.tool_key == tool_key,
                or_(ToolDefinition.org_id == org_id, ToolDefinition.org_id.is_(None)),
                ToolDefinition.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def save(self, tool: ToolDefinition, updates: dict) -> ToolDefinition:
        for key, value in updates.items():
            setattr(tool, key, value)
        await self._session.flush()
        await self._session.refresh(tool)
        return tool

    async def list_executions(
        self,
        org_id: str,
        *,
        tool_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
        execution_type: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> list[ToolExecution]:
        stmt = select(ToolExecution).where(ToolExecution.org_id == org_id)
        if tool_id:
            stmt = stmt.where(ToolExecution.tool_id == tool_id)
        if agent_id:
            stmt = stmt.where(ToolExecution.agent_id == agent_id)
        if status:
            stmt = stmt.where(ToolExecution.status == status)
        if execution_type:
            stmt = stmt.where(ToolExecution.execution_type == execution_type)
        stmt = stmt.order_by(ToolExecution.created_at.desc()).offset((page - 1) * size).limit(size)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_executions(
        self,
        org_id: str,
        *,
        tool_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
        execution_type: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(ToolExecution).where(ToolExecution.org_id == org_id)
        if tool_id:
            stmt = stmt.where(ToolExecution.tool_id == tool_id)
        if agent_id:
            stmt = stmt.where(ToolExecution.agent_id == agent_id)
        if status:
            stmt = stmt.where(ToolExecution.status == status)
        if execution_type:
            stmt = stmt.where(ToolExecution.execution_type == execution_type)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_recent_executions(
        self,
        org_id: str,
        *,
        tool_id: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[ToolExecution]:
        stmt = select(ToolExecution).where(ToolExecution.org_id == org_id)
        if tool_id:
            stmt = stmt.where(ToolExecution.tool_id == tool_id)
        if since:
            stmt = stmt.where(ToolExecution.created_at >= since)
        stmt = stmt.order_by(ToolExecution.created_at.desc())
        if limit:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_execution(self, execution: ToolExecution) -> ToolExecution:
        self._session.add(execution)
        await self._session.flush()
        await self._session.refresh(execution)
        return execution
