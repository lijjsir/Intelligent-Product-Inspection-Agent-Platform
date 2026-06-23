from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentName = Literal[
    "evidence",
    "vision",
    "lab_detection",
    "quality_analysis",
    "memory_governance",
    "file",
]


class AgentRouteDecision(BaseModel):
    """AgentManager 路由决策结果"""
    selected_agent: AgentName = "quality_analysis"
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
        "evidence_arbitration",
        "vision_inspection",
        "lab_detection",
        "quality_analysis",
        "memory_governance",
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
    status: Literal["completed", "failed", "blocked"] = "completed"
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
    owner_agent: AgentName = "quality_analysis"
    capability: str = ""
    operation: str = ""
    mode: Literal["answer", "report", "action"] = "answer"
    input: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)  # kept for backward compat
    parallel_group: str | None = None
    required: bool = True
    expected_artifact: str | None = None


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


class CapabilityContext(BaseModel):
    """Context passed to capability handlers — everything they need to execute."""
    step: Any = Field(default=None)  # AgentPlanStep
    state: Any = Field(default=None)  # ManagerState
    request: Any = Field(default=None)  # NormalizedRequest
    db_session: Any = None
    extra: dict[str, Any] = Field(default_factory=dict)


from agent.router.errors import (
    AgentBlockedError,
    AgentCapabilityError,
    AgentDataError,
    AgentDispatchError,
    AgentErrorCategory,
    AgentErrorStatus,
    AgentExecutionError,
    AgentExternalServiceError,
    AgentInternalError,
    AgentModelError,
    AgentPermissionError,
    AgentRoutingError,
    AgentRuntimeError,
    AgentTimeoutError,
    AgentToolError,
    AgentValidationError,
    make_agent_error,
)
