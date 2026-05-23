"""Agent tool contracts — ToolSpec, ToolCall, ToolResult, ToolContext, ToolExecution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolSpec:
    """Unified tool specification for LLM consumption and internal orchestration."""

    name: str
    title: str
    description: str

    agent_scope: list[str] = field(default_factory=list)
    surfaces: list[str] = field(default_factory=list)

    mode: Literal["read", "write", "action"] = "read"
    risk_level: Literal["low", "medium", "high"] = "medium"

    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    requires_confirmation: bool = False
    enabled: bool = True
    timeout_ms: int = 30_000
    version: str = "1.0.0"

    # Internal handler path: dotted string like "agent.tools.builtin.rag_tools.rag_retrieve"
    handler: str = ""

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }

    def to_prompt_text(self) -> str:
        params = self.input_schema or {}
        return (
            f"- {self.name}: {self.description}\n"
            f"  parameters: {params.get('properties', {})}"
        )


@dataclass
class ToolContext:
    org_id: str
    request_id: str
    agent: str = ""
    surface: str = ""
    user_id: str | None = None
    workflow_run_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    allowed_modes: list[str] = field(default_factory=list)
    confirmed_actions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None


@dataclass
class ToolResult:
    tool_name: str
    status: Literal["success", "failed", "blocked", "skipped"]
    data: dict[str, Any] | None = None
    error: str | None = None
    execution_id: str | None = None
    latency_ms: int | None = None


@dataclass
class ToolExecution:
    id: str
    tool_name: str
    agent_name: str
    surface: str
    request_id: str
    status: Literal["success", "failed", "blocked", "skipped"]
    workflow_run_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    input_json: dict[str, Any] = field(default_factory=dict)
    output_json: dict[str, Any] | None = None
    error_message: str | None = None
    latency_ms: int = 0
    created_at: str = ""
