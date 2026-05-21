"""Resolve agent-available tools from bindings and active tool versions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import AgentToolBinding, ToolDefinition, ToolVersion


class ToolResolver:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def resolve_for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        bindings_result = await self._session.execute(
            select(AgentToolBinding).where(
                AgentToolBinding.org_id == self._org_id,
                AgentToolBinding.agent_id == agent_id,
                AgentToolBinding.binding_status == "active",
            )
        )
        bindings = list(bindings_result.scalars().all())
        if not bindings:
            return []

        tool_ids = [binding.tool_id for binding in bindings]
        tools_result = await self._session.execute(
            select(ToolDefinition).where(
                ToolDefinition.id.in_(tool_ids),
                ToolDefinition.status == "active",
                ToolDefinition.deleted_at.is_(None),
            )
        )
        tools = {tool.id: tool for tool in tools_result.scalars().all()}

        versions: dict[str, ToolVersion] = {}
        for binding in bindings:
            version_result = await self._session.execute(
                select(ToolVersion).where(
                    ToolVersion.id == binding.tool_version_id,
                    ToolVersion.org_id == self._org_id,
                )
            )
            version = version_result.scalar_one_or_none()
            if version:
                versions[version.id] = version

        resolved = []
        for binding in bindings:
            tool = tools.get(binding.tool_id)
            version = versions.get(binding.tool_version_id)
            if not tool or not version:
                continue
            resolved.append(self._tool_to_llm_schema(tool, version))
        return resolved

    async def resolve_tool(self, tool_key: str) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(ToolDefinition).where(
                ToolDefinition.tool_key == tool_key,
                or_(ToolDefinition.org_id == self._org_id, ToolDefinition.org_id.is_(None)),
                ToolDefinition.deleted_at.is_(None),
            )
        )
        tool = result.scalar_one_or_none()
        if not tool:
            return None

        version = None
        if tool.active_version_id:
            version_result = await self._session.execute(
                select(ToolVersion).where(
                    ToolVersion.id == tool.active_version_id,
                    ToolVersion.org_id == self._org_id,
                )
            )
            version = version_result.scalar_one_or_none()

        if not version:
            return None
        return self._tool_to_llm_schema(tool, version)

    @staticmethod
    def _tool_to_llm_schema(tool: ToolDefinition, version: ToolVersion) -> dict[str, Any]:
        return {
            "name": tool.tool_key,
            "description": tool.description or version.description or "",
            "parameters": version.parameters_schema or {"type": "object", "properties": {}},
            "returns": version.returns_schema or {"type": "object", "properties": {}},
        }
