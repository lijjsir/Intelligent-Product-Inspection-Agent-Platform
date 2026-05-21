from __future__ import annotations

from typing import Any
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.schemas.common import PageParams


class AgentDefinitionBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., max_length=100, description="Agent name")
    description: Optional[str] = Field(default=None, description="Agent description")
    prompt_version_id: Optional[str] = Field(default=None, description="Associated prompt version ID")
    workflow_binding: Optional[str] = Field(default=None, max_length=100, description="Workflow binding")
    intent_config_id: Optional[str] = Field(default=None, description="Intent config ID")
    subgraph_key: str = Field(default="quality_judgement", max_length=64, description="Bound subgraph key")
    entry_graph: Optional[str] = Field(default=None, max_length=128, description="Entry graph identifier")
    supports_start_stop: bool = Field(default=True, description="Whether runtime supports start/stop")
    graph_version: str = Field(default="v1", max_length=32, description="Graph version")
    is_active: bool = Field(default=True, description="Whether agent is active")
    lifecycle_status: str = Field(default="active", max_length=32, description="active/partial/planned/legacy/deprecated")
    group_key: str = Field(default="core", max_length=32, description="core/memory/planned/legacy")
    route_enabled: bool = Field(default=True, description="是否参与路由")
    supports_route_toggle: bool = Field(default=True, description="是否允许暂停恢复路由")
    customer_visible_description: Optional[str] = Field(default=None, description="给客户看的能力说明")

    @field_validator(
        "description",
        "prompt_version_id",
        "workflow_binding",
        "intent_config_id",
        "entry_graph",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v


class AgentDefinitionCreate(AgentDefinitionBase):
    pass


class AgentDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    prompt_version_id: Optional[str] = None
    workflow_binding: Optional[str] = None
    intent_config_id: Optional[str] = None
    subgraph_key: Optional[str] = Field(default=None, max_length=64)
    entry_graph: Optional[str] = Field(default=None, max_length=128)
    supports_start_stop: Optional[bool] = None
    graph_version: Optional[str] = Field(default=None, max_length=32)
    is_active: Optional[bool] = None


class AgentDefinitionResponse(AgentDefinitionBase):
    id: str
    org_id: str
    runtime_status: Optional[str] = None
    metrics_summary: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentDefinitionListQuery(PageParams):
    name: Optional[str] = None
    is_active: Optional[bool] = None

    def to_filters(self) -> dict:
        return {k: v for k, v in self.model_dump(exclude={"page", "size"}).items() if v is not None}


class PromptVersionBase(BaseModel):
    name: str = Field(..., max_length=100, description="Prompt name")
    content: str = Field(..., description="Prompt content")
    version: int = Field(default=1, ge=1, description="Version number")
    status: str = Field(default="draft", description="Status: draft/review/approved/deprecated")


class PromptVersionCreate(PromptVersionBase):
    pass


class PromptVersionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    content: Optional[str] = None
    version: Optional[int] = None
    status: Optional[str] = None


class PromptVersionResponse(PromptVersionBase):
    id: str
    org_id: str
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptVersionListQuery(PageParams):
    name: Optional[str] = None
    status: Optional[str] = None

    def to_filters(self) -> dict:
        return {k: v for k, v in self.model_dump(exclude={"page", "size"}).items() if v is not None}


class IntentRouteBase(BaseModel):
    intent_name: str = Field(..., max_length=100, description="Intent name")
    agent_id: Optional[str] = Field(None, description="Associated agent ID")
    priority: int = Field(default=0, ge=0, description="Priority for routing")
    sample_count: int = Field(default=0, ge=0, description="Number of samples")
    is_active: bool = Field(default=True, description="Whether route is active")


class IntentRouteCreate(IntentRouteBase):
    pass


class IntentRouteUpdate(BaseModel):
    intent_name: Optional[str] = Field(None, max_length=100)
    agent_id: Optional[str] = None
    priority: Optional[int] = None
    sample_count: Optional[int] = None
    is_active: Optional[bool] = None


class IntentRouteResponse(IntentRouteBase):
    id: str
    org_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntentRouteListQuery(PageParams):
    intent_name: Optional[str] = None
    is_active: Optional[bool] = None

    def to_filters(self) -> dict:
        return {k: v for k, v in self.model_dump(exclude={"page", "size"}).items() if v is not None}


class RagAnalysisStats(BaseModel):
    total_queries: int = Field(default=0, description="Total RAG queries")
    avg_hit_rate: float = Field(default=0.0, description="Average hit rate")
    avg_citation_coverage: float = Field(default=0.0, description="Average citation coverage")
    empty_recall_count: int = Field(default=0, description="Empty recall count")
    avg_latency_ms: float = Field(default=0.0, description="Average latency in ms")


class RagAnalysisBreakdownItem(BaseModel):
    key: str
    label: str
    value: int = 0
    avg_hit_rate: float = 0.0
    avg_citation_coverage: float = 0.0


class RagAnalysisOption(BaseModel):
    key: str
    label: str


class RagEvidenceImpactItem(BaseModel):
    rule_key: str
    verdicts: list[str] = Field(default_factory=list)
    source_count: int = 0
    query_count: int = 0
    sources: list[str] = Field(default_factory=list)


class RagAnalysisItem(BaseModel):
    task_id: str
    session_id: Optional[str] = Field(default=None, description="Chat session ID if available")
    query: Optional[str] = Field(default=None, description="Query text if available")
    rag_space_id: Optional[str] = None
    rag_space_name: Optional[str] = None
    hit_count: int = 0
    hit_rate: float
    citation_coverage: float
    latency_ms: float
    source_agent: Optional[str] = None
    source_graph: Optional[str] = None
    sub_route: Optional[str] = None
    trace_id: Optional[str] = None
    top_score: Optional[float] = None
    product_id: Optional[str] = None
    verdict: Optional[str] = None
    expectation_matched: Optional[bool] = None
    evidence_found: bool = False
    evidence_used: bool = False
    verdict_impacted: bool = False
    top_sources: list[str] = Field(default_factory=list)
    rule_hits: list[str] = Field(default_factory=list)
    created_at: datetime


class RagTraceDetailResponse(BaseModel):
    trace_id: str
    query: Optional[str] = None
    rag_space_id: Optional[str] = None
    rag_space_name: Optional[str] = None
    source_agent: Optional[str] = None
    source_graph: Optional[str] = None
    sub_route: Optional[str] = None
    top_k: int = 0
    hit_count: int = 0
    hit_rate: float = 0.0
    citation_coverage: float = 0.0
    latency_ms: float = 0.0
    top_score: Optional[float] = None
    product_family: Optional[str] = None
    expectation_matched: Optional[bool] = None
    evidence_found: bool = False
    evidence_used: bool = False
    verdict_impacted: bool = False
    retrieval_config: dict[str, Any] = Field(default_factory=dict)
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    used_citations: list[dict[str, Any]] = Field(default_factory=list)
    rule_hits: list[str] = Field(default_factory=list)
    verdict: Optional[str] = None
    answer: Optional[str] = None
    result: Any = None
    top_sources: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class RagAnalysisResponse(BaseModel):
    stats: RagAnalysisStats
    space_options: list[RagAnalysisOption] = Field(default_factory=list)
    source_agent_options: list[RagAnalysisOption] = Field(default_factory=list)
    space_breakdown: list[RagAnalysisBreakdownItem] = Field(default_factory=list)
    source_agent_breakdown: list[RagAnalysisBreakdownItem] = Field(default_factory=list)
    evidence_impact: list[RagEvidenceImpactItem] = Field(default_factory=list)
    recent_items: list[RagAnalysisItem]


class AgentRuntimeOverviewResponse(BaseModel):
    active_agents: int = 0
    running_agents: int = 0
    stopped_agents: int = 0
    total_executions: int = 0
    avg_latency_ms: float = 0.0
    queued_tasks: int = 0
    completed_today: int = 0
    success_rate: float = 0.0
    recent_errors: int = 0


class AgentRuntimeInstanceResponse(BaseModel):
    runtime_key: str
    agent_id: str
    agent_name: str
    subgraph_key: str
    status: str
    supports_start_stop: bool
    is_active: bool
    execution_count: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    last_executed_at: Optional[datetime] = None
    last_started_at: Optional[datetime] = None
    last_stopped_at: Optional[datetime] = None
    runtime_status: str = "stopped"
    lifecycle_status: Optional[str] = None
    group_key: Optional[str] = None
    route_enabled: bool = True
    supports_route_toggle: bool = True
    customer_visible_description: Optional[str] = None
    last_error_message: Optional[str] = None
    maintenance_reason: Optional[str] = None


class TopologyNode(BaseModel):
    id: str
    label: str
    kind: str
    subgraph_key: Optional[str] = None
    agent_name: Optional[str] = None
    status: Optional[str] = None
    lifecycle_status: Optional[str] = None
    route_enabled: Optional[bool] = None
    execution_count: Optional[int] = None
    avg_latency_ms: Optional[float] = None
    last_started_at: Optional[datetime] = None


class TopologyEdge(BaseModel):
    source: str
    target: str


class AgentTopologyResponse(BaseModel):
    selected_subgraph: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    intent_name: Optional[str] = None
    agent_name: Optional[str] = None


class RoutingSignalDescriptor(BaseModel):
    key: str
    label: str
    description: str
    source_stage: str


class RoutingPriorityRule(BaseModel):
    order: int
    when: str
    target_subgraph: str
    reason: str
    examples: list[str] = Field(default_factory=list)
    stop_on_match: bool = True


class RoutingDecisionCard(BaseModel):
    key: str
    title: str
    target_subgraph: str
    reason: str
    priority_order: int
    matched_signals: list[str] = Field(default_factory=list)
    summary: str


class RoutingSubgraphDescriptor(BaseModel):
    subgraph_key: str
    label: str
    summary: str
    entry_node: str
    nodes: list[TopologyNode] = Field(default_factory=list)
    edges: list[TopologyEdge] = Field(default_factory=list)
    typical_scenarios: list[str] = Field(default_factory=list)


class RoutingStrategyOverviewResponse(BaseModel):
    route_mode: str
    default_target: str
    root_graph: AgentTopologyResponse
    subgraphs: list[RoutingSubgraphDescriptor] = Field(default_factory=list)
    priority_rules: list[RoutingPriorityRule] = Field(default_factory=list)
    signals: list[RoutingSignalDescriptor] = Field(default_factory=list)
    decision_cards: list[RoutingDecisionCard] = Field(default_factory=list)
    registered_route_count: int = 0
    registered_intents: list[str] = Field(default_factory=list)


class AgentRuntimeEventResponse(BaseModel):
    id: str
    org_id: str
    agent_id: str
    runtime_key: str
    event_type: str
    before_status: Optional[str] = None
    after_status: Optional[str] = None
    reason: Optional[str] = None
    operator_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentDetailResponse(AgentDefinitionResponse):
    """Agent 详情 — 包含绑定资源和操作记录"""
    bound_prompt_version: Optional[PromptVersionResponse] = None
    bound_routes: list[IntentRouteResponse] = Field(default_factory=list)
    runtime_events: list[AgentRuntimeEventResponse] = Field(default_factory=list)


class PauseRouteRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="暂停原因")


# === Routing Strategy Viewer schemas (non-config version) ===

class RouteAgentDescriptor(BaseModel):
    key: str  # "chat" | "inspection_task"
    label: str  # "Quality Chat" | "Inspection Task Agent"
    sub_routes: list[str] = Field(default_factory=list)  # ["general_chat", "rag_qa"]


class RouteRuleDescriptor(BaseModel):
    priority: int  # 1-7
    name: str  # "图片检测意图"
    condition_summary: str  # "图片附件 + 检测/质检意图"
    target_agent: str  # "chat" | "inspection_task"
    target_sub_route: str  # "inspection_execute"
    route_source: str = "builtin"  # "builtin" | "manual"
    examples: list[str] = Field(default_factory=list)


class RouteSignalInfo(BaseModel):
    key: str
    label: str
    description: str
    detected: bool = False


class RoutingCurrentResponse(BaseModel):
    mode: str = "rule_first_with_model_fallback"
    mode_label: str = "规则优先，模型兜底"
    default_agent: str = "chat"
    default_sub_route: str = "general_chat"
    agents: list[RouteAgentDescriptor] = Field(default_factory=list)
    rules: list[RouteRuleDescriptor] = Field(default_factory=list)
    signals: list[RouteSignalInfo] = Field(default_factory=list)
    rule_count: int = 0
    active_agent_count: int = 0


class RouteSimulateRequest(BaseModel):
    query: str = Field(default="", description="用户输入文本")
    has_image: bool = Field(default=False)
    has_structured_file: bool = Field(default=False)
    has_rag_space: bool = Field(default=False)
    force_agent: Optional[str] = Field(default=None, description="手动强制指定 agent")


class RouteSimulateResponse(BaseModel):
    matched_rule_name: str = ""
    matched_priority: int = 0
    selected_agent: str = ""
    selected_sub_route: str = ""
    route_source: str = ""
    reason: str = ""
    signals: dict = Field(default_factory=dict)
    is_fallback: bool = False


class RouteEventItem(BaseModel):
    id: str
    created_at: datetime
    selected_agent: str
    sub_route: Optional[str] = None
    route_source: str
    reason: Optional[str] = None
    intent_name: Optional[str] = None
    confidence: float = 0.0
    latency_ms: int = 0
    blocked: bool = False
    blocked_reason: Optional[str] = None
    request_summary: Optional[str] = None


class RoutingMetricsResponse(BaseModel):
    total_24h: int = 0
    rule_hit_count: int = 0
    model_fallback_count: int = 0
    blocked_count: int = 0
    avg_latency_ms: float = 0.0
    by_agent: dict = Field(default_factory=dict)
    by_rule: dict = Field(default_factory=dict)
