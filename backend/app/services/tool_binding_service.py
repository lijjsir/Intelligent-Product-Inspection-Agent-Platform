from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import uuid7
from app.models.tool import AgentToolBinding
from app.repositories.tool_binding_repo import ToolBindingRepository
from app.repositories.tool_repo import ToolRepository
from app.repositories.tool_version_repo import ToolVersionRepository


class ToolBindingService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._tool_repo = ToolRepository(session)
        self._binding_repo = ToolBindingRepository(session)
        self._version_repo = ToolVersionRepository(session)

    async def list_bindings(self, tool_id: str | None = None) -> list[dict[str, Any]]:
        if tool_id:
            bindings = await self._binding_repo.list_by_tool(self._org_id, tool_id)
        else:
            bindings = await self._binding_repo.list_all(self._org_id)
        return [await self._serialize(b) for b in bindings]

    async def create_binding(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = payload["agent_id"]
        tool_id = payload["tool_id"]

        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")

        existing = await self._binding_repo.get_by_agent_and_tool(
            self._org_id, agent_id, tool_id
        )
        if existing:
            raise ValidationError("binding already exists for this agent and tool")

        tool_version_id = payload.get("tool_version_id") or tool.active_version_id or tool.id
        binding = AgentToolBinding(
            id=str(uuid7()),
            org_id=self._org_id,
            agent_id=agent_id,
            tool_id=tool_id,
            tool_version_id=tool_version_id,
            binding_status="active",
            allowed_intents=payload.get("allowed_intents"),
            approval_required=bool(payload.get("approval_required", False)),
            auto_call_enabled=bool(payload.get("auto_call_enabled", True)),
        )
        binding = await self._binding_repo.create(binding)
        return await self._serialize(binding)

    async def update_binding(self, binding_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        binding = await self._binding_repo.get(self._org_id, binding_id)
        if not binding:
            raise NotFoundError("binding not found")
        allowed = {
            "auto_call_enabled", "approval_required", "allowed_intents", "binding_status",
        }
        updates = {k: v for k, v in payload.items() if k in allowed and v is not None}
        if updates:
            binding = await self._binding_repo.save(binding, updates)
        return await self._serialize(binding)

    async def delete_binding(self, binding_id: str) -> dict[str, Any]:
        binding = await self._binding_repo.get(self._org_id, binding_id)
        if not binding:
            raise NotFoundError("binding not found")
        await self._binding_repo.delete(binding)
        return {"deleted": True}

    async def _serialize(self, binding: AgentToolBinding) -> dict[str, Any]:
        tool = await self._tool_repo.get(self._org_id, binding.tool_id)
        version = await self._version_repo.get(self._org_id, binding.tool_version_id)
        return {
            "id": binding.id,
            "agent_id": binding.agent_id,
            "agent_name": binding.agent_id,
            "tool_id": binding.tool_id,
            "tool_name": tool.display_name if tool else binding.tool_id,
            "tool_version_id": binding.tool_version_id,
            "tool_version": version.version if version else "unknown",
            "binding_status": binding.binding_status,
            "auto_call_enabled": binding.auto_call_enabled,
            "approval_required": binding.approval_required,
            "allowed_scenarios": binding.allowed_intents or [],
            "rate_limit": None,
            "created_at": binding.created_at,
            "updated_at": binding.updated_at,
        }
