from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.integrations.bk_aidev.mcp_client import McpToolDescriptor
from app.api.v1 import tools as tools_api
from app.schemas.user import CurrentUser
from app.services.tool_import_service import ToolImportService
from app.services.tool_service import ToolService


class FakeDiscoveryClient:
    async def list_tools(self):
        return [
            McpToolDescriptor(
                name="quality_lookup",
                description="Look up quality records",
                input_schema={
                    "type": "object",
                    "properties": {"batch_no": {"type": "string"}},
                },
            )
        ]


def test_mcp_candidate_bounds_long_description_for_database_display_name():
    descriptor = McpToolDescriptor(
        name="quality_lookup",
        description="x" * 300,
        input_schema={"type": "object", "properties": {}},
    )

    candidate = descriptor.to_candidate()

    assert len(candidate["display_name"]) == 256
    assert candidate["description"] == "x" * 300


@pytest.mark.asyncio
async def test_mcp_preview_uses_adapter_and_includes_storage_metadata(monkeypatch):
    monkeypatch.setattr(
        ToolImportService,
        "_build_mcp_client",
        staticmethod(lambda server_url, transport: FakeDiscoveryClient()),
    )
    service = ToolImportService(SimpleNamespace(), "org-1")

    candidates = await service.preview_mcp_tools(
        "http://127.0.0.1:9000/mcp",
        "streamable_http",
    )

    assert candidates == [
        {
            "tool_key": "mcp.quality_lookup",
            "mcp_tool_name": "quality_lookup",
            "display_name": "Look up quality records",
            "description": "Look up quality records",
            "parameters_schema": {
                "type": "object",
                "properties": {"batch_no": {"type": "string"}},
            },
            "returns_schema": {"type": "object", "properties": {}},
            "tool_type": "mcp",
            "category": "MCP",
            "source_type": "mcp",
            "endpoint": "http://127.0.0.1:9000/mcp",
            "transport": "streamable_http",
        }
    ]


@pytest.mark.asyncio
async def test_mcp_import_persists_server_transport_and_original_tool_name(monkeypatch):
    monkeypatch.setattr(
        ToolImportService,
        "_build_mcp_client",
        staticmethod(lambda server_url, transport: FakeDiscoveryClient()),
    )

    class FakeToolRepo:
        def __init__(self):
            self.created = None
            self.saved_updates = None

        async def get_by_tool_key(self, org_id, tool_key):
            return None

        async def create(self, tool):
            self.created = tool
            return tool

        async def save(self, tool, updates):
            self.saved_updates = updates
            tool.active_version_id = updates["active_version_id"]
            return tool

    class FakeVersionRepo:
        def __init__(self):
            self.created = None

        async def create(self, version):
            self.created = version
            return version

    service = ToolImportService(SimpleNamespace(), "org-1")
    tool_repo = FakeToolRepo()
    version_repo = FakeVersionRepo()
    service._repo = tool_repo
    service._version_repo = version_repo

    imported = await service.import_mcp_tools(
        "http://127.0.0.1:9000/mcp",
        ["mcp.quality_lookup"],
        "sse",
    )

    assert imported[0]["tool_key"] == "mcp.quality_lookup"
    assert tool_repo.created.source_ref == "http://127.0.0.1:9000/mcp"
    assert tool_repo.created.status == "draft"
    assert version_repo.created.endpoint == "http://127.0.0.1:9000/mcp"
    assert version_repo.created.retry_policy["transport"] == "sse"
    assert version_repo.created.retry_policy["mcp_tool_name"] == "quality_lookup"
    assert tool_repo.saved_updates == {"active_version_id": version_repo.created.id}


@pytest.mark.asyncio
async def test_tool_service_executes_mcp_through_adapter(monkeypatch):
    captured: dict = {}

    class FakeCallClient:
        def __init__(self, server_url, **kwargs):
            captured["server_url"] = server_url
            captured.update(kwargs)

        async def call_tool(self, tool_name, arguments):
            captured["tool_name"] = tool_name
            captured["arguments"] = arguments
            return {"status": "ok"}

    monkeypatch.setattr("app.services.tool_service.McpClientAdapter", FakeCallClient)
    service = ToolService(SimpleNamespace(), "org-1")
    tool = SimpleNamespace(tool_type="mcp", tool_key="mcp.quality_lookup")
    version = SimpleNamespace(
        endpoint="http://127.0.0.1:9000/mcp",
        timeout_ms=12000,
        retry_policy={
            "transport": "sse",
            "mcp_tool_name": "quality_lookup",
            "retries": 2,
        },
    )

    result = await service._execute_tool_for_test(tool, version, {"batch_no": "B-100"})

    assert result == {"status": "ok"}
    assert captured == {
        "server_url": "http://127.0.0.1:9000/mcp",
        "transport": "sse",
        "timeout_seconds": 12.0,
        "retries": 2,
        "tool_name": "quality_lookup",
        "arguments": {"batch_no": "B-100"},
    }


@pytest.mark.asyncio
async def test_mcp_import_api_forwards_transport_and_selected_tools(monkeypatch):
    captured: dict = {}

    class FakeImportService:
        def __init__(self, db, org_id):
            captured["org_id"] = org_id

        async def import_mcp_tools(self, server_url, selected_keys, transport):
            captured.update(
                server_url=server_url,
                selected_keys=selected_keys,
                transport=transport,
            )
            return [{"id": "tool-1", "tool_key": "mcp.quality_lookup"}]

    monkeypatch.setattr(tools_api, "ToolImportService", FakeImportService)
    response = await tools_api.import_mcp_tools(
        payload={
            "server_url": "http://127.0.0.1:9000/mcp",
            "transport": "sse",
            "tool_keys": ["mcp.quality_lookup"],
        },
        current=CurrentUser(
            user_id="developer-1",
            org_id="org-1",
            role="app_developer",
            roles=["app_developer"],
        ),
        db=object(),
    )

    assert response.data["imported"][0]["tool_key"] == "mcp.quality_lookup"
    assert captured == {
        "org_id": "org-1",
        "server_url": "http://127.0.0.1:9000/mcp",
        "selected_keys": ["mcp.quality_lookup"],
        "transport": "sse",
    }
