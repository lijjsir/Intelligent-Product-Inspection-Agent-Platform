from __future__ import annotations

from typing import Any

import httpx
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from agent.integrations.bk_aidev.mcp_client import McpClientAdapter, McpClientError
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.ids import uuid7
from app.models.tool import ToolDefinition, ToolVersion
from app.repositories.tool_repo import ToolRepository
from app.repositories.tool_version_repo import ToolVersionRepository


class ToolImportService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ToolRepository(session)
        self._version_repo = ToolVersionRepository(session)

    async def preview_openapi(self, source: str) -> list[dict[str, Any]]:
        spec = await self._load_openapi_spec(source)
        candidates: list[dict[str, Any]] = []

        for path, methods in spec.get("paths", {}).items():
            for method, operation in methods.items():
                if method not in {"get", "post", "put", "delete", "patch"}:
                    continue
                candidates.append(
                    {
                        "tool_key": operation.get(
                            "operationId",
                            f"openapi.{method}.{path.lstrip('/').replace('/', '.')}",
                        ),
                        "display_name": operation.get("summary", f"{method.upper()} {path}"),
                        "description": operation.get("description", ""),
                        "endpoint": path,
                        "method": method.upper(),
                        "parameters_schema": self._extract_params_schema(operation),
                        "returns_schema": self._extract_response_schema(operation),
                        "tool_type": "http",
                        "category": "http_api",
                        "source_type": "openapi",
                    }
                )
        return candidates

    async def import_openapi_tools(
        self,
        source: str,
        selected_keys: list[str],
    ) -> list[dict[str, Any]]:
        candidates = await self.preview_openapi(source)
        imported = []

        for candidate in candidates:
            if candidate["tool_key"] not in selected_keys:
                continue

            existing = await self._repo.get_by_tool_key(self._org_id, candidate["tool_key"])
            if existing:
                raise ValidationError(f"tool {candidate['tool_key']} already exists")

            tool = ToolDefinition(
                id=str(uuid7()),
                org_id=self._org_id,
                tool_key=str(candidate["tool_key"]),
                display_name=self._bounded_display_name(candidate),
                description=str(candidate.get("description") or ""),
                category="http_api",
                tool_type="http",
                status="draft",
                risk_level="medium",
                is_readonly=True,
                source_type="openapi",
                source_ref=source if source.startswith(("http://", "https://")) else None,
                manifest_hash=None,
                health_status="unknown",
                created_by=None,
            )
            tool = await self._repo.create(tool)

            version = ToolVersion(
                id=str(uuid7()),
                org_id=self._org_id,
                tool_id=tool.id,
                version="1.0.0",
                display_name=tool.display_name,
                description=tool.description,
                endpoint=str(candidate.get("endpoint") or ""),
                method=str(candidate.get("method") or "GET"),
                handler_path=None,
                parameters_schema=candidate.get("parameters_schema") or {"type": "object", "properties": {}},
                returns_schema=candidate.get("returns_schema") or {"type": "object", "properties": {}},
                auth_type="none",
                secret_ref=None,
                timeout_ms=30000,
                retry_policy=None,
                rate_limit_rpm=60,
                status="draft",
                created_by=None,
            )
            version = await self._version_repo.create(version)
            await self._repo.save(tool, {"active_version_id": version.id})

            imported.append(
                {
                    "id": tool.id,
                    "tool_key": tool.tool_key,
                    "display_name": tool.display_name,
                    "status": tool.status,
                }
            )

        return imported

    async def preview_mcp_tools(
        self,
        server_url: str,
        transport: str = "streamable_http",
    ) -> list[dict[str, Any]]:
        try:
            descriptors = await self._build_mcp_client(server_url, transport).list_tools()
        except McpClientError as exc:
            raise ValidationError(str(exc)) from exc

        return [
            {
                **descriptor.to_candidate(),
                "endpoint": server_url,
                "transport": transport,
            }
            for descriptor in descriptors
        ]

    async def import_mcp_tools(
        self,
        server_url: str,
        selected_keys: list[str],
        transport: str = "streamable_http",
    ) -> list[dict[str, Any]]:
        candidates = await self.preview_mcp_tools(server_url, transport)
        imported: list[dict[str, Any]] = []

        for candidate in candidates:
            if candidate["tool_key"] not in selected_keys:
                continue

            existing = await self._repo.get_by_tool_key(self._org_id, candidate["tool_key"])
            if existing:
                raise ValidationError(f"tool {candidate['tool_key']} already exists")

            tool = await self._repo.create(
                ToolDefinition(
                    id=str(uuid7()),
                    org_id=self._org_id,
                    tool_key=str(candidate["tool_key"]),
                    display_name=self._bounded_display_name(candidate),
                    description=str(candidate.get("description") or ""),
                    category="MCP",
                    tool_type="mcp",
                    status="draft",
                    risk_level="medium",
                    is_readonly=False,
                    source_type="mcp",
                    source_ref=server_url,
                    manifest_hash=None,
                    health_status="unknown",
                    created_by=None,
                )
            )

            version = await self._version_repo.create(
                ToolVersion(
                    id=str(uuid7()),
                    org_id=self._org_id,
                    tool_id=tool.id,
                    version="1.0.0",
                    display_name=tool.display_name,
                    description=tool.description,
                    endpoint=server_url,
                    method="MCP",
                    handler_path=None,
                    parameters_schema=candidate.get("parameters_schema")
                    or {"type": "object", "properties": {}},
                    returns_schema=candidate.get("returns_schema")
                    or {"type": "object", "properties": {}},
                    auth_type="none",
                    secret_ref=None,
                    timeout_ms=settings.mcp_timeout_seconds * 1000,
                    retry_policy={
                        "transport": transport,
                        "mcp_tool_name": candidate["mcp_tool_name"],
                        "retries": settings.mcp_retries,
                    },
                    rate_limit_rpm=60,
                    status="draft",
                    created_by=None,
                )
            )
            await self._repo.save(tool, {"active_version_id": version.id})
            imported.append(
                {
                    "id": tool.id,
                    "tool_key": tool.tool_key,
                    "display_name": tool.display_name,
                    "status": tool.status,
                }
            )

        return imported

    @staticmethod
    def _build_mcp_client(server_url: str, transport: str) -> McpClientAdapter:
        return McpClientAdapter(
            server_url,
            transport=transport,
            timeout_seconds=settings.mcp_timeout_seconds,
            retries=settings.mcp_retries,
        )

    @staticmethod
    def _bounded_display_name(candidate: dict[str, Any]) -> str:
        value = str(candidate.get("display_name") or candidate.get("tool_key") or "").strip()
        return value[:256]

    async def _load_openapi_spec(self, source: str) -> dict[str, Any]:
        if source.startswith("http://") or source.startswith("https://"):
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(source)
                resp.raise_for_status()
                text = resp.text
        else:
            text = source

        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError:
            import json

            return json.loads(text)

    @staticmethod
    def _extract_params_schema(operation: dict[str, Any]) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in operation.get("parameters", []):
            properties[param["name"]] = {
                "type": param.get("schema", {}).get("type", "string"),
                "description": param.get("description", ""),
            }
            if param.get("required"):
                required.append(param["name"])

        if "requestBody" in operation:
            content = operation["requestBody"].get("content", {})
            json_body = content.get("application/json", {})
            schema = json_body.get("schema", {})
            if schema:
                return schema

        return {"type": "object", "properties": properties, "required": required}

    @staticmethod
    def _extract_response_schema(operation: dict[str, Any]) -> dict[str, Any]:
        responses = operation.get("responses", {})
        success = responses.get("200") or responses.get("201") or {}
        content = success.get("content", {})
        json_body = content.get("application/json", {})
        return json_body.get("schema", {"type": "object", "properties": {}})
