from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.integrations.bk_aidev.approval_bridge import (
    decrypt_tool_arguments,
    encrypt_tool_arguments,
)
from agent.integrations.bk_aidev.context_compression import compress_history
from agent.integrations.bk_aidev.mcp_client import McpClientAdapter, McpClientError
from agent.integrations.bk_aidev.tool_safety import ToolSafetyPolicy, sanitize_tool_output
from agent.tools.contracts import ToolContext, ToolSpec
from agent.tools.invoker import ToolInvoker
from agent.tools.registry import ToolRegistry


class FakeMcpTool:
    name = "quality_lookup"
    description = "Look up quality records"

    def get_input_jsonschema(self):
        return {
            "type": "object",
            "properties": {"batch_no": {"type": "string"}},
            "required": ["batch_no"],
        }

    async def ainvoke(self, arguments):
        return {"batch_no": arguments["batch_no"], "status": "ok"}


class FakeMcpClient:
    def __init__(self, config, recorded):
        recorded.append(config)

    async def get_tools(self, server_name):
        assert server_name == "quality"
        return [FakeMcpTool()]


@pytest.mark.asyncio
async def test_mcp_adapter_discovers_and_invokes_tools():
    recorded: list[dict] = []
    adapter = McpClientAdapter(
        "http://127.0.0.1:9000/mcp",
        transport="sse",
        server_name="quality",
        client_factory=lambda config: FakeMcpClient(config, recorded),
    )

    descriptors = await adapter.list_tools()
    result = await adapter.call_tool("quality_lookup", {"batch_no": "B-100"})

    assert descriptors[0].to_candidate()["tool_key"] == "mcp.quality_lookup"
    assert descriptors[0].input_schema["required"] == ["batch_no"]
    assert result == {"batch_no": "B-100", "status": "ok"}
    assert recorded[0]["quality"]["transport"] == "sse"


def test_mcp_adapter_rejects_invalid_server_url():
    with pytest.raises(McpClientError, match="must start with"):
        McpClientAdapter("localhost:9000/mcp")


def test_tool_safety_redacts_and_truncates_output():
    output = sanitize_tool_output(
        {"token": "secret-token", "content": "x" * 500},
        ToolSafetyPolicy(max_output_chars=256, sensitive_values=("secret-token",)),
    )

    assert output is not None
    assert output["truncated"] is True
    assert "secret-token" not in output["content"]
    assert "***REDACTED***" in output["content"]


def test_tool_safety_redacts_sensitive_field_names_without_configured_values():
    output = sanitize_tool_output(
        {"api_key": "not-configured", "nested": {"password": "plain-text"}},
        ToolSafetyPolicy(),
    )

    assert output == {
        "api_key": "***REDACTED***",
        "nested": {"password": "***REDACTED***"},
    }


def test_tool_approval_arguments_are_encrypted_at_rest():
    arguments = {"task_id": "task-1", "token": "secret-token"}

    encrypted = encrypt_tool_arguments(arguments)

    assert "secret-token" not in encrypted
    assert decrypt_tool_arguments(encrypted) == arguments


def test_context_compression_preserves_latest_messages_within_budget():
    messages = [
        {"role": "user", "content": f"question-{index}-" + "x" * 300}
        for index in range(10)
    ]

    compressed, stats = compress_history(
        messages,
        max_chars=700,
        keep_recent=3,
        per_message_chars=240,
    )

    assert compressed[-1]["content"].startswith("question-9-")
    assert stats.original_messages == 10
    assert stats.dropped_messages > 0
    assert stats.kept_chars <= 700


@pytest.mark.asyncio
async def test_tool_invoker_creates_approval_for_confirmation(monkeypatch):
    registry = ToolRegistry()

    async def handler(arguments, context):
        return {"executed": True}

    registry.register(
        ToolSpec(
            name="quality.execute",
            title="Execute quality task",
            description="Execute a high-risk task",
            mode="action",
            risk_level="high",
            requires_confirmation=True,
        ),
        handler,
    )

    async def fake_create_tool_approval(**kwargs):
        return {"id": "approval-1", "status": "pending"}

    monkeypatch.setattr(
        "agent.tools.invoker.create_tool_approval",
        fake_create_tool_approval,
    )
    invoker = ToolInvoker(registry, db_session=SimpleNamespace())
    result = await invoker.invoke(
        tool_name="quality.execute",
        arguments={"task_id": "task-1"},
        context=ToolContext(
            org_id="org-1",
            request_id="request-1",
            user_id="user-1",
            agent="quality_analysis",
            surface="quality_task",
            allowed_modes=["action"],
        ),
    )

    assert result.status == "blocked"
    assert result.data == {"approval": {"id": "approval-1", "status": "pending"}}
    assert "requires confirmation" in str(result.error)


@pytest.mark.asyncio
async def test_tool_invoker_records_redacted_payload_and_preserves_token_counts(monkeypatch):
    registry = ToolRegistry()

    async def handler(arguments, context):
        return {"token": arguments["token"], "input_tokens": 12}

    registry.register(
        ToolSpec(
            name="quality.lookup",
            title="Quality lookup",
            description="Look up quality data",
        ),
        handler,
    )

    class FakeToolRepo:
        def __init__(self, session):
            self.session = session

        async def get_by_tool_key(self, org_id, tool_key):
            return SimpleNamespace(id="00000000-0000-0000-0000-000000000010")

    class FakeSession:
        def __init__(self):
            self.items = []

        def add(self, item):
            self.items.append(item)

        async def flush(self):
            return None

    monkeypatch.setattr("app.repositories.tool_repo.ToolRepository", FakeToolRepo)
    session = FakeSession()
    result = await ToolInvoker(registry, db_session=session).invoke(
        tool_name="quality.lookup",
        arguments={"token": "secret-token"},
        context=ToolContext(org_id="org-1", request_id="request-1"),
    )

    assert result.data == {"token": "***REDACTED***", "input_tokens": 12}
    assert len(session.items) == 1
    execution = session.items[0]
    assert execution.input_payload == {"token": "***REDACTED***"}
    assert execution.output_payload["input_tokens"] == 12
