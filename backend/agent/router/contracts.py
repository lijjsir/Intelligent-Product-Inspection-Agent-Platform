from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AgentRouteDecision(BaseModel):
    """AgentManager 路由决策结果"""
    selected_agent: Literal["chat", "file", "inspection_task"] = "chat"
    sub_route: Literal[
        "general_chat",
        "rag_qa",
        "quality_qa",
        "task_create",
        "inspection_execute",
        "image_understanding",
        "file_summary",
        "file_qa",
        "paper_format_check",
        "quality_report_query",
        "quality_task_status",
        "action_blocked",
        "data_analysis",
        "rag_ingest",
        "error",  # Added for architecture refactor error propagation
    ] = "general_chat"
    intent: str = "general_chat"
    confidence: float = 1.0
    reason: str = ""
    requires_confirmation: bool = False
    route_source: Literal["rule", "manual", "model", "fallback", "manager"] = "rule"
    fallback_agent: str | None = None


class AgentRouterInput(BaseModel):
    """AgentManager 路由输入 — 从 NormalizedRequest 提取关键信号"""
    query: str = ""
    request_kind: str = "chat"
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    route_hints: dict[str, Any] = Field(default_factory=dict)
    ext: dict[str, Any] = Field(default_factory=dict)


class AgentRouterOutput(BaseModel):
    """AgentManager 输出，包装原始 Agent 输出 + 路由元信息"""
    route_decision: AgentRouteDecision
    agent_output: dict[str, Any] = Field(default_factory=dict)
    status: Literal["completed", "failed", "degraded", "blocked"] = "completed"
    degrade_reason: str | None = None
    error: dict[str, Any] | None = None


class Capability(BaseModel):
    key: str
    owner_agents: list[str] = Field(default_factory=list)
    handler: str = ""
    operation: str
    mode: Literal["answer", "report", "action"]
    surfaces: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    cost_level: Literal["low", "medium", "high"] = "medium"
    allow_parallel: bool = True
    description: str = ""


class AgentPlanStep(BaseModel):
    step_id: str
    owner_agent: str = ""  # was Literal["chat", "file", "inspection_task"]; relaxed for backward compat
    capability: str = ""  # relaxed for backward compat with capability_key
    operation: str = ""
    mode: Literal["answer", "report", "action"] = "answer"
    input: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)  # kept for backward compat
    parallel_group: str | None = None
    required: bool = True
    expected_artifact: str | None = None

    # Backward compat aliases (will be removed in Phase 2)
    capability_key: str = ""  # deprecated, use capability
    agent: str = ""  # deprecated, use owner_agent

    @model_validator(mode="after")
    def _sync_backward_compat_fields(self):
        """Sync old/new field names bidirectionally so both consumers work."""
        # Sync capability <-> capability_key
        if self.capability and not self.capability_key:
            self.capability_key = self.capability
        if self.capability_key and not self.capability:
            self.capability = self.capability_key

        # Sync owner_agent <-> agent
        _VALID_AGENTS = {"chat", "file", "inspection_task"}
        if self.owner_agent and not self.agent:
            self.agent = self.owner_agent
        if self.agent and not self.owner_agent:
            if self.agent in _VALID_AGENTS:
                self.owner_agent = self.agent

        return self


class AgentRoutePlan(BaseModel):
    plan_id: str
    surface: str
    goal: str
    steps: list[AgentPlanStep]
    success_criteria: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    max_iterations: int = 3


class AgentObservation(BaseModel):
    step_id: str
    capability_key: str
    owner_agent: str = ""
    agent: str = ""  # deprecated, kept for backward compat
    status: Literal["success", "failed", "blocked", "skipped"]
    summary: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class AgentArtifact(BaseModel):
    artifact_id: str
    type: str
    source_agent: str
    status: Literal["success", "empty", "failed", "blocked"] = "success"
    content: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    needs_user_input: bool = False
    empty_result: bool = False
    error: dict[str, Any] | None = None
    created_at: str | None = None


class NodeSpec(BaseModel):
    node_key: str
    accepted_input_kinds: list[str] = Field(default_factory=list)
    required_model_types: list[str] = Field(default_factory=list)
    mode: Literal["answer", "report", "action"]
    output_artifact_types: list[str] = Field(default_factory=list)


class AgentRuntimeError(Exception):
    """Base exception for all agent runtime errors. Always visible to frontend by default."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        frontend_visible: bool = True,
        detail: dict | None = None,
    ):
        self.code = code
        self.message = message
        self.frontend_visible = frontend_visible
        self.detail = detail or {}
        super().__init__(message)


class AgentDispatchError(AgentRuntimeError):
    """Raised when dispatcher cannot route to a business agent."""
    pass


class AgentCapabilityError(AgentRuntimeError):
    """Raised when a capability is unsupported or fails."""
    pass


class AgentExecutionError(AgentRuntimeError):
    """Raised when a business agent fails to execute."""
    pass


class AgentValidationError(AgentRuntimeError):
    """Raised when plan validation fails."""
    pass
