from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRouteDecision(BaseModel):
    """AgentManager 路由决策结果"""
    selected_agent: Literal["chat", "inspection_task"] = "chat"
    sub_route: Literal[
        "general_chat",
        "rag_qa",
        "quality_qa",
        "task_create",
        "inspection_execute",
        "image_understanding",
        "file_summary",
        "file_qa",
        "quality_report_query",
        "quality_task_status",
        "action_blocked",
        "data_analysis",
        "rag_ingest",
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


class Capability(BaseModel):
    key: str
    agent: str
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
    capability_key: str
    agent: str
    operation: str
    mode: Literal["answer", "report", "action"]
    input: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    parallel_group: str | None = None
    required: bool = True


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
    agent: str
    status: Literal["success", "failed", "blocked", "skipped"]
    summary: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class AgentArtifact(BaseModel):
    artifact_id: str
    type: str
    source_agent: str
    content: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    created_at: str | None = None


class NodeSpec(BaseModel):
    node_key: str
    accepted_input_kinds: list[str] = Field(default_factory=list)
    required_model_types: list[str] = Field(default_factory=list)
    mode: Literal["answer", "report", "action"]
    output_artifact_types: list[str] = Field(default_factory=list)
