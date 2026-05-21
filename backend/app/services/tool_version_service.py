from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import uuid7
from app.models.tool import ToolVersion
from app.repositories.tool_repo import ToolRepository
from app.repositories.tool_version_repo import ToolVersionRepository


class ToolVersionService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._tool_repo = ToolRepository(session)
        self._version_repo = ToolVersionRepository(session)

    async def list_versions(self, tool_id: str) -> list[dict[str, Any]]:
        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")
        versions = await self._version_repo.list_by_tool(self._org_id, tool_id)
        return [self._serialize(v) for v in versions]

    async def create_version(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")

        base_version = None
        if tool.active_version_id:
            base_version = await self._version_repo.get(self._org_id, tool.active_version_id)
        if not base_version:
            versions = await self._version_repo.list_by_tool(self._org_id, tool_id)
            base_version = versions[0] if versions else None

        existing = await self._version_repo.get_by_tool_and_version(
            self._org_id, tool_id, payload["version"]
        )
        if existing:
            raise ValidationError(f"version {payload['version']} already exists")

        version = ToolVersion(
            id=str(uuid7()),
            org_id=self._org_id,
            tool_id=tool.id,
            version=payload["version"],
            display_name=payload.get("display_name", tool.display_name),
            description=payload.get("description", tool.description),
            endpoint=payload.get("endpoint", base_version.endpoint if base_version else None),
            method=payload.get("method", base_version.method if base_version else None),
            handler_path=payload.get("handler_path", base_version.handler_path if base_version else None),
            parameters_schema=payload.get(
                "parameters_schema",
                base_version.parameters_schema if base_version else {"type": "object", "properties": {}},
            ),
            returns_schema=payload.get(
                "returns_schema",
                base_version.returns_schema if base_version else {"type": "object", "properties": {}},
            ),
            auth_type=payload.get("auth_type", base_version.auth_type if base_version else "none"),
            secret_ref=payload.get("secret_ref", base_version.secret_ref if base_version else None),
            timeout_ms=int(payload.get("timeout_ms", base_version.timeout_ms if base_version else 30000)),
            retry_policy=payload.get("retry_policy", base_version.retry_policy if base_version else None),
            rate_limit_rpm=int(payload.get("rate_limit_rpm", base_version.rate_limit_rpm if base_version else 60)),
            status="draft",
            created_by=None,
        )
        version = await self._version_repo.create(version)
        return self._serialize(version)

    async def publish_version(self, tool_id: str, version_id: str) -> dict[str, Any]:
        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")
        version = await self._version_repo.get(self._org_id, version_id)
        if not version or version.tool_id != tool.id:
            raise NotFoundError("version not found")

        version = await self._version_repo.save(version, {"status": "active"})
        await self._tool_repo.save(
            tool, {"active_version_id": version.id, "version": version.version}
        )
        return {"success": True, "active_version": version.version}

    async def rollback_version(self, tool_id: str, version_id: str) -> dict[str, Any]:
        tool = await self._tool_repo.get(self._org_id, tool_id)
        if not tool:
            raise NotFoundError("tool not found")
        version = await self._version_repo.get(self._org_id, version_id)
        if not version or version.tool_id != tool.id:
            raise NotFoundError("version not found")

        await self._tool_repo.save(
            tool, {"active_version_id": version.id, "version": version.version}
        )
        return {"success": True, "active_version": version.version}

    def _serialize(self, version: ToolVersion) -> dict[str, Any]:
        return {
            "id": version.id,
            "tool_id": version.tool_id,
            "version": version.version,
            "display_name": version.display_name,
            "description": version.description or "",
            "endpoint": version.endpoint,
            "method": version.method,
            "handler_path": version.handler_path,
            "parameters_schema": version.parameters_schema or {},
            "returns_schema": version.returns_schema or {},
            "auth_type": version.auth_type,
            "timeout_ms": version.timeout_ms,
            "retry_policy": version.retry_policy,
            "rate_limit_rpm": version.rate_limit_rpm,
            "status": version.status,
            "created_by": version.created_by or "system",
            "created_at": version.created_at,
            "updated_at": version.updated_at,
        }
