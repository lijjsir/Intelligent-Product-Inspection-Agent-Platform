from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class NormalizedAttachment(BaseModel):
    id: str | None = None
    name: str | None = None
    url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    kind: str = "file"


class ClarificationRequest(BaseModel):
    missing_fields: list[str] = Field(default_factory=list)
    reason: str = ""
    suggestions: list[str] = Field(default_factory=list)
    examples: dict[str, str] = Field(default_factory=dict)


class NormalizedRequest(BaseModel):
    request_kind: Literal["chat", "task"] = "chat"
    request_id: str
    workflow_run_id: str | None = None
    session_id: str | None = None
    assistant_message_id: str | None = None
    org_id: str
    user_id: str | None = None
    workspace: str = "app"
    plan_tier: str = "basic"
    capabilities: list[str] = Field(default_factory=list)
    query: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    ext: dict[str, Any] = Field(default_factory=dict)
    attachments: list[NormalizedAttachment] = Field(default_factory=list)
    product_id: str | None = None
    spec_code: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    route_hints: dict[str, Any] = Field(default_factory=dict)


class RouteSignals(BaseModel):
    attachment_types: list[str] = Field(default_factory=list)
    has_non_pdf_documents: bool = False
    has_images: bool = False
    has_task_keyword: bool = False
    has_file_attachments: bool = False
    needs_external_knowledge: bool = False
    request_kind: str = "chat"
    selected_rag_space_id: str | None = None


class RouteDecision(BaseModel):
    mode: Literal["legacy_only", "canary_non_pdf", "router_enabled"] = "legacy_only"
    selected_subgraph: Literal["quality_judgement"] = "quality_judgement"
    fallback_subgraph: Literal["quality_judgement"] = "quality_judgement"
    reason: str = ""
    signals: RouteSignals = Field(default_factory=RouteSignals)


class TaskAggregate(BaseModel):
    id: str | None = None
    product_id: str | None = None
    spec_code: str | None = None
    status: str | None = None
    priority: int | None = None
    image_count: int | None = None
    created_at: str | None = None


class ResultAggregate(BaseModel):
    id: str | None = None
    task_id: str | None = None
    verdict: str | None = None
    overall_score: float | None = None
    llm_model: str | None = None
    citations: dict[str, Any] | None = None
    reasoning_chain: dict[str, Any] | None = None


class StabilityAggregate(BaseModel):
    risk_score: float | None = None
    risk_level: str | None = None
    evidence_score: float | None = None
    confidence_score: float | None = None
    traceability_score: float | None = None
    faithfulness_score: float | None = None
    physical_hallucination_score: float | None = None


class AlertEvent(BaseModel):
    severity: str
    title: str
    message: str


class TokenUsageEvent(BaseModel):
    model_key: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_amount: float = 0.0
    trace_id: str | None = None


class QualityTraceEvent(BaseModel):
    trace_id: str | None = None
    trace_url: str | None = None
    workflow_version: str | None = None
    prompt_version: str | None = None
    route_subgraph: str | None = None


class RagQueryLog(BaseModel):
    query: str
    rag_space_id: str | None = None
    hit_count: int = 0
    hit_rate: float = 0.0
    citation_coverage: float = 0.0
    latency_ms: float = 0.0
    source_graph: str = "quality_judgement"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersistableOutput(BaseModel):
    task: TaskAggregate | None = None
    result: ResultAggregate | None = None
    stability: StabilityAggregate | None = None
    alerts: list[AlertEvent] = Field(default_factory=list)
    token_usage: list[TokenUsageEvent] = Field(default_factory=list)
    quality_trace: QualityTraceEvent | None = None
    rag_queries: list[RagQueryLog] = Field(default_factory=list)


class AgentOutput(BaseModel):
    message_type: str = "assistant_text"
    answer: str = ""
    summary: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    result_card: dict[str, Any] | None = None
    expectation_check: dict[str, Any] | None = None
    rag_summary: dict[str, Any] | None = None
    action_state: str | None = None
    task_draft: dict[str, Any] | None = None
    created_task: dict[str, Any] | None = None
    clarification: ClarificationRequest | None = None
    route_decision: RouteDecision | None = None
    persistable_output: PersistableOutput = Field(default_factory=PersistableOutput)
    raw_state: dict[str, Any] = Field(default_factory=dict)
