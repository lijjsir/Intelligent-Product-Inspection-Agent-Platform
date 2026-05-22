"""Memory governance contracts.

Pure Pydantic contracts with no ORM, FastAPI, or LangGraph runtime dependencies.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator
from app.core.datetime import utcnow


# ---- Enums ----

class Workspace(str, Enum):
    APP = "app"
    OPS = "ops"
    GOVERNANCE = "governance"


class MemoryType(str, Enum):
    USER_PREFERENCE = "user_preference"
    TASK_EPISODE = "task_episode"
    INSPECTION_PATTERN = "inspection_pattern"
    RAG_USAGE_MEMORY = "rag_usage_memory"
    AGENT_OPS_MEMORY = "agent_ops_memory"
    GOVERNANCE_MEMORY = "governance_memory"


class MemoryStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    ISOLATED = "isolated"
    DISABLED = "disabled"
    DELETED = "deleted"
    EXPIRED = "expired"


class EventType(str, Enum):
    INPUT_RECEIVED = "input.received"
    RAG_RETRIEVED = "rag.retrieved"
    TOOL_CALLED = "tool.called"
    AGENT_MESSAGE_CREATED = "agent.message_created"
    MEMORY_CANDIDATE_CREATED = "memory.candidate_created"
    MEMORY_WRITE_CREATED = "memory.write_created"
    MEMORY_WRITE_REJECTED = "memory.write_rejected"
    MEMORY_RETRIEVAL_COMPLETED = "memory.retrieval_completed"
    MEMORY_CONFLICT_DETECTED = "memory.conflict_detected"
    MEMORY_PROPAGATION_GRAPH_CREATED = "memory.propagation_graph_created"
    MEMORY_ROLLBACK_PLANNED = "memory.rollback_planned"
    MEMORY_ROLLBACK_APPLIED = "memory.rollback_applied"
    MEMORY_EVALUATION_COMPLETED = "memory.evaluation_completed"
    MEMORY_DEGRADED = "memory.degraded"


class EdgeType(str, Enum):
    DERIVED_FROM = "derived_from"
    READ_BY = "read_by"
    USED_AS_TOOL_PARAM = "used_as_tool_param"
    CITED_AS_EVIDENCE = "cited_as_evidence"
    VERSION_OF = "version_of"
    MERGED_FROM = "merged_from"
    CONFLICTS_WITH = "conflicts_with"
    SUMMARIZED_FROM = "summarized_from"
    PLANNED_FROM = "planned_from"
    ROLLBACK_DEPENDS_ON = "rollback_depends_on"


class RollbackAction(str, Enum):
    DELETE = "delete"
    DEGRADE = "degrade"
    ISOLATE = "isolate"
    PATCH = "patch"
    BRANCH = "branch"


class ReviewStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---- Write ----

class MemorySource(BaseModel):
    kind: str
    task_id: str | None = None
    trace_id: str | None = None


class MemoryContent(BaseModel):
    summary: str = Field(..., min_length=1)
    facts: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class MemoryScope(BaseModel):
    task_id: str | None = None
    product_line: str | None = None
    rag_space_id: str | None = None
    role: str | None = None


class MemoryWriteRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    user_id: str | None = None
    workspace: Workspace
    source: MemorySource
    memory_type: MemoryType
    scope: MemoryScope | None = None
    content: MemoryContent
    evidence_pointers: dict | None = None
    version_parent_id: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    ttl_policy: str = "90d"
    privacy_level: str = "tenant_private"
    created_by_type: str = "agent"
    created_by: str | None = None
    trace_id: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_consistency(self) -> MemoryWriteRequest:
        if self.memory_type == MemoryType.USER_PREFERENCE and not self.user_id:
            raise ValueError("user_preference requires user_id")
        if self.memory_type == MemoryType.TASK_EPISODE:
            has_task = (self.scope and self.scope.task_id) or (self.source and self.source.task_id)
            if not has_task:
                raise ValueError("task_episode requires task_id in scope or source")
        if self.memory_type == MemoryType.INSPECTION_PATTERN:
            if not self.scope or not self.scope.product_line:
                raise ValueError("inspection_pattern requires product_line in scope")
        if self.memory_type == MemoryType.RAG_USAGE_MEMORY:
            if not self.scope or not self.scope.rag_space_id:
                raise ValueError("rag_usage_memory requires rag_space_id in scope")
        if self.memory_type == MemoryType.AGENT_OPS_MEMORY and self.workspace != Workspace.OPS:
            raise ValueError("agent_ops_memory must use ops workspace")
        if self.memory_type == MemoryType.GOVERNANCE_MEMORY and self.workspace != Workspace.GOVERNANCE:
            raise ValueError("governance_memory must use governance workspace")
        return self


class MemoryWriteResponse(BaseModel):
    memory_id: str
    status: MemoryStatus
    trust_score: float | None = None
    confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)


# ---- Search ----

class ScopeFilter(BaseModel):
    memory_type: list[MemoryType] | None = None
    product_line: str | None = None
    rag_space_id: str | None = None
    task_id: str | None = None


class MemorySearchRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    user_id: str | None = None
    workspace: Workspace
    query: str = Field(..., min_length=1)
    scope_filter: ScopeFilter | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class MemorySearchItem(BaseModel):
    memory_id: str
    memory_type: str
    summary: str
    score: float
    confidence: float | None = None
    trust_score: float | None = None
    source: dict | None = None
    usage_policy: str = "context_only"
    warnings: list[str] = Field(default_factory=list)


class MemorySearchResponse(BaseModel):
    memory_context: dict | None = None
    items: list[MemorySearchItem] = Field(default_factory=list)
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_context(self) -> MemorySearchResponse:
        if self.memory_context is None:
            self.memory_context = {
                "items": [item.model_dump() for item in self.items],
                "warnings": self.warnings,
                "degraded": self.degraded,
            }
        return self


# ---- Events ----

class MemoryEventPayload(BaseModel):
    event_id: str = Field(..., min_length=1)
    org_id: str = Field(..., min_length=1)
    user_id: str | None = None
    workspace: Workspace
    event_type: EventType
    source_kind: str | None = None
    agent_id: str | None = None
    role: str | None = None
    task_id: str | None = None
    trace_id: str | None = None
    memory_id: str | None = None
    payload_json: dict | None = None
    payload_ref: str | None = None
    risk_tags: dict | None = None
    parent_event_ids: list[str] | None = None
    created_at: datetime = Field(default_factory=lambda: utcnow())


# ---- Propagation ----

class MemoryPropagationRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    workspace: str = "governance"
    root_memory_id: str = Field(..., min_length=1)
    trace_id: str | None = None
    max_depth: int = Field(default=4, ge=1, le=10)
    include_edge_types: list[EdgeType] = Field(default_factory=lambda: [
        EdgeType.DERIVED_FROM,
        EdgeType.READ_BY,
        EdgeType.USED_AS_TOOL_PARAM,
        EdgeType.VERSION_OF,
    ])


class PropagationNode(BaseModel):
    memory_id: str
    classification: str
    depth: int
    edge_type: str | None = None
    affected_by: list[str] = Field(default_factory=list)


class MemoryPropagationResponse(BaseModel):
    root_memory_id: str
    nodes: list[PropagationNode] = Field(default_factory=list)
    direct_contaminated: list[str] = Field(default_factory=list)
    indirect_contaminated: list[str] = Field(default_factory=list)
    suspected: list[str] = Field(default_factory=list)
    clean_boundary: list[str] = Field(default_factory=list)


# ---- Rollback ----

class MemoryRollbackRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    workspace: Workspace
    operator_id: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    root_memory_id: str = Field(..., min_length=1)
    rollback_action: RollbackAction
    target_memory_ids: list[str] = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    require_human_review: bool = False
    propagation_graph: dict | None = None


class MemoryRollbackResponse(BaseModel):
    rollback_id: str
    root_memory_id: str
    action: RollbackAction
    affected_count: int
    review_status: ReviewStatus
    before_snapshot: dict | None = None
    after_snapshot: dict | None = None


# ---- Evaluation ----

class MemoryEvaluationRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    workspace: str = "governance"
    rollback_id: str = Field(..., min_length=1)
    task_id: str | None = None
    trace_id: str | None = None
    scenario: str | None = None


class MemoryEvaluationResponse(BaseModel):
    evaluation_id: str
    rollback_id: str
    scenario: str | None = None
    metrics: dict | None = None
    replay_result: dict | None = None
    conclusion: str | None = None


# ---- Policy ----

class MemoryPolicyContract(BaseModel):
    org_id: str = Field(..., min_length=1)
    workspace: Workspace
    policy_key: str
    policy_type: str
    config: dict
    status: str = "active"

    @staticmethod
    def defaults(policy_type: str) -> dict:
        if policy_type == "write_gate":
            return {
                "min_confidence_for_active": 0.75,
                "isolate_on_rag_conflict": True,
                "require_review_for_governance_memory": True,
                "reject_no_source": True,
                "reject_no_trace": True,
                "reject_no_scope": True,
            }
        if policy_type == "retrieval":
            return {"default_top_k": 5, "max_top_k": 10}
        if policy_type == "rollback":
            return {"require_human_review_for_cross_user": True, "require_human_review_for_cross_role": True}
        if policy_type == "audit":
            return {"log_all_reads": True, "log_all_writes": True, "log_all_rollbacks": True}
        return {}
