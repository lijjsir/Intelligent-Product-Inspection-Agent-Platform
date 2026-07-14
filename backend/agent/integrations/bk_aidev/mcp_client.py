"""MCP client adapter based on the bk-aidev-agent resource-manager design."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

McpTransport = Literal["streamable_http", "sse"]


class McpClientError(RuntimeError):
    """Raised when MCP discovery or invocation fails."""


@dataclass(frozen=True)
class McpToolDescriptor:
    name: str
    description: str
    input_schema: dict[str, Any]

    def to_candidate(self) -> dict[str, Any]:
        display_name = (self.description.strip() or self.name)[:256]
        return {
            "tool_key": f"mcp.{self.name}",
            "mcp_tool_name": self.name,
            "display_name": display_name,
            "description": self.description,
            "parameters_schema": self.input_schema,
            "returns_schema": {"type": "object", "properties": {}},
            "tool_type": "mcp",
            "category": "MCP",
            "source_type": "mcp",
        }


class McpClientAdapter:
    """Discover and invoke tools from one MCP server with retries and timeouts."""

    _SUPPORTED_TRANSPORTS = {"streamable_http", "sse"}

    def __init__(
        self,
        server_url: str,
        *,
        transport: McpTransport = "streamable_http",
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        retries: int = 1,
        server_name: str = "default",
        client_factory: Callable[[dict[str, dict[str, Any]]], Any] | None = None,
    ) -> None:
        self.server_url = server_url.strip()
        self.transport = str(transport or "streamable_http").strip().lower()
        self.headers = dict(headers or {})
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.retries = max(0, int(retries))
        self.server_name = server_name.strip() or "default"
        self._client_factory = client_factory
        self._validate()

    async def list_tools(
        self,
        selected_names: Iterable[str] | None = None,
    ) -> list[McpToolDescriptor]:
        selected = {str(name).strip() for name in (selected_names or []) if str(name).strip()}
        tools = await self._load_tools()
        return [
            McpToolDescriptor(
                name=str(tool.name),
                description=str(getattr(tool, "description", "") or ""),
                input_schema=self._tool_input_schema(tool),
            )
            for tool in tools
            if not selected or str(tool.name) in selected
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        normalized_name = tool_name.strip()
        if not normalized_name:
            raise McpClientError("MCP tool name is required")

        tools = await self._load_tools()
        tool = next((item for item in tools if str(item.name) == normalized_name), None)
        if tool is None:
            raise McpClientError(f"MCP tool '{normalized_name}' was not found")

        async def invoke() -> Any:
            return await asyncio.wait_for(
                tool.ainvoke(dict(arguments or {})),
                timeout=self.timeout_seconds,
            )

        result = await self._retry(invoke, action=f"invoke tool {normalized_name}")
        return self._normalize_result(result)

    async def _load_tools(self) -> list[Any]:
        async def load() -> list[Any]:
            client = self._build_client()
            result = await asyncio.wait_for(
                client.get_tools(server_name=self.server_name),
                timeout=self.timeout_seconds,
            )
            return list(result or [])

        return await self._retry(load, action="discover tools")

    async def _retry(self, operation: Callable[[], Any], *, action: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return await operation()
            except Exception as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
        logger.warning("MCP %s failed for %s", action, self.server_url, exc_info=last_error)
        raise McpClientError(f"MCP {action} failed: {last_error}") from last_error

    def _build_client(self) -> Any:
        config = {
            self.server_name: {
                "url": self.server_url,
                "transport": self.transport,
                **({"headers": self.headers} if self.headers else {}),
            }
        }
        if self._client_factory is not None:
            return self._client_factory(config)
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError as exc:
            raise McpClientError(
                "langchain-mcp-adapters is required for MCP tool execution"
            ) from exc
        return MultiServerMCPClient(config)

    def _validate(self) -> None:
        if not self.server_url.startswith(("http://", "https://")):
            raise McpClientError("MCP server URL must start with http:// or https://")
        if self.transport not in self._SUPPORTED_TRANSPORTS:
            supported = ", ".join(sorted(self._SUPPORTED_TRANSPORTS))
            raise McpClientError(f"unsupported MCP transport '{self.transport}'; use {supported}")

    @staticmethod
    def _tool_input_schema(tool: Any) -> dict[str, Any]:
        get_schema = getattr(tool, "get_input_jsonschema", None)
        if callable(get_schema):
            schema = get_schema()
            if isinstance(schema, dict):
                return schema

        args_schema = getattr(tool, "args_schema", None)
        if isinstance(args_schema, dict):
            return args_schema
        model_json_schema = getattr(args_schema, "model_json_schema", None)
        if callable(model_json_schema):
            schema = model_json_schema()
            if isinstance(schema, dict):
                return schema
        return {"type": "object", "properties": {}}

    @classmethod
    def _normalize_result(cls, value: Any) -> dict[str, Any]:
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            value = model_dump(mode="json")
        elif hasattr(value, "content"):
            value = {
                "content": cls._json_safe(getattr(value, "content", None)),
                "artifact": cls._json_safe(getattr(value, "artifact", None)),
                "status": getattr(value, "status", None),
            }

        normalized = cls._json_safe(value)
        if isinstance(normalized, dict):
            return normalized
        if isinstance(normalized, list):
            return {"items": normalized}
        return {"content": normalized}

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe(item) for item in value]
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return cls._json_safe(model_dump(mode="json"))
        return str(value)
