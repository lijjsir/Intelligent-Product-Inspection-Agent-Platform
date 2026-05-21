"""Security and access control for tool execution."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import AgentToolBinding, ToolDefinition


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""
    requires_approval: bool = False


class ToolGuard:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def check(self, agent_id: str, tool_key: str) -> GuardResult:
        tool_result = await self._session.execute(
            select(ToolDefinition).where(
                ToolDefinition.tool_key == tool_key,
                or_(ToolDefinition.org_id == self._org_id, ToolDefinition.org_id.is_(None)),
                ToolDefinition.deleted_at.is_(None),
            )
        )
        tool = tool_result.scalar_one_or_none()
        if not tool:
            return GuardResult(False, f"tool {tool_key} not found")

        if tool.status != "active":
            return GuardResult(False, f"tool {tool_key} is {tool.status}")

        binding_result = await self._session.execute(
            select(AgentToolBinding).where(
                AgentToolBinding.org_id == self._org_id,
                AgentToolBinding.agent_id == agent_id,
                AgentToolBinding.tool_id == tool.id,
                AgentToolBinding.binding_status == "active",
            )
        )
        binding = binding_result.scalar_one_or_none()
        if not binding:
            return GuardResult(False, f"agent {agent_id} is not bound to tool {tool_key}")

        if tool.risk_level == "high" and binding.approval_required:
            return GuardResult(True, "requires approval", requires_approval=True)

        return GuardResult(True)
