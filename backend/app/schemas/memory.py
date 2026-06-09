from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


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
    CONTESTED = "contested"


class UsagePolicy(str, Enum):
    CONTEXT_ONLY = "context_only"


class PrivacyLevel(str, Enum):
    TENANT_PRIVATE = "tenant_private"


class EventType(str, Enum):
    INPUT_RECEIVED = "input.received"
    RAG_RETRIEVED = "rag.retrieved"
    TOOL_CALLED = "tool.called"
    AGENT_MESSAGE_CREATED = "agent.message_created"
    MEMORY_CANDIDATE_CREATED = "memory.candidate_created"
    MEMORY_CANDIDATE_SUPPORTED = "memory.candidate_supported"
    MEMORY_CANDIDATE_MERGED = "memory.candidate_merged"
    MEMORY_CANDIDATE_REJECTED = "memory.candidate_rejected"
    MEMORY_PROMOTED_TO_ACTIVE = "memory.promoted_to_active"
    MEMORY_WRITE_CREATED = "memory.write_created"
    MEMORY_WRITE_REJECTED = "memory.write_rejected"
    MEMORY_RETRIEVAL_COMPLETED = "memory.retrieval_completed"
    MEMORY_CONFLICT_DETECTED = "memory.conflict_detected"
    MEMORY_PROPAGATION_GRAPH_CREATED = "memory.propagation_graph_created"
    MEMORY_ROLLBACK_PLANNED = "memory.rollback_planned"
    MEMORY_ROLLBACK_APPLIED = "memory.rollback_applied"
    MEMORY_EVALUATION_COMPLETED = "memory.evaluation_completed"


PROVENANCE_EDGE_VALUES = {
    "version_of",
    "summarized_from",
    "merged_from",
    "derived_from",
    "cited_as_evidence",
    "planned_from",
    "rollback_depends_on",
}


class EdgeType(str, Enum):
    # Provenance edges: written by system context during memory write.
    VERSION_OF = "version_of"
    SUMMARIZED_FROM = "summarized_from"
    MERGED_FROM = "merged_from"
    DERIVED_FROM = "derived_from"
    CITED_AS_EVIDENCE = "cited_as_evidence"
    PLANNED_FROM = "planned_from"
    ROLLBACK_DEPENDS_ON = "rollback_depends_on"

    # Semantic edge: only conflicts_with is persisted (has actionable value —
    # next retrieval can check existing conflicts and skip LLM detection).
    CONFLICTS_WITH = "conflicts_with"

    # Audit-only edges — NOT for default propagation, NOT for semantic relation.
    READ_BY = "read_by"
    USED_AS_TOOL_PARAM = "used_as_tool_param"


class MemoryDependencyInput(BaseModel):
    """Explicit provenance dependency declaration in write request."""
    target_memory_id: str = Field(..., min_length=1)
    edge_type: EdgeType
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def validate_provenance_edge(self) -> MemoryDependencyInput:
        if self.edge_type.value not in PROVENANCE_EDGE_VALUES:
            raise ValueError("dependency_edges only accepts provenance edge types")
        return self


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


class PolicyType(str, Enum):
    WRITE_GATE = "write_gate"
    RETRIEVAL = "retrieval"
    ROLLBACK = "rollback"
    AUDIT = "audit"


# ---- Write Request ----

class MemorySource(BaseModel):
    kind: str = Field(..., description="user / web / rag / tool / agent_message / human_review")
    task_id: str | None = None
    trace_id: str | None = None
    agent_id: str | None = None


class MemoryContent(BaseModel):
    summary: str = Field(..., min_length=1, description="Structured summary")
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
    source: MemorySource
    memory_type: MemoryType
    scope: MemoryScope | None = None
    content: MemoryContent
    evidence_pointers: dict | None = None
    version_parent_id: str | None = None
    dependency_edges: list[MemoryDependencyInput] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    ttl_policy: str = Field(default="90d")
    privacy_level: PrivacyLevel = Field(default=PrivacyLevel.TENANT_PRIVATE)
    created_by_type: str = Field(default="agent")
    created_by: str | None = None
    trace_id: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_consistency(self) -> MemoryWriteRequest:
        if self.memory_type == MemoryType.USER_PREFERENCE and not self.user_id:
            raise ValueError("user_preference requires user_id")
        if self.memory_type == MemoryType.TASK_EPISODE:
            if not self.scope or not self.scope.task_id:
                if not self.source.task_id:
                    raise ValueError("task_episode requires task_id in scope or source")
        if self.memory_type == MemoryType.INSPECTION_PATTERN:
            if not self.scope or not self.scope.product_line:
                raise ValueError("inspection_pattern requires product_line in scope")
        if self.memory_type == MemoryType.RAG_USAGE_MEMORY:
            if not self.scope or not self.scope.rag_space_id:
                raise ValueError("rag_usage_memory requires rag_space_id in scope")
        return self


class MemoryWriteResponse(BaseModel):
    memory_id: str
    status: MemoryStatus
    trust_score: float | None = None
    confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)
    policy_key: str | None = None
    policy_version: str | None = None


class ExtractedMemory(BaseModel):
    org_id: str = Field(..., min_length=1)
    user_id: str | None = None
    memory_type: MemoryType
    summary: str = Field(..., min_length=1)
    facts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    scope: dict = Field(default_factory=dict)
    evidence_pointers: dict = Field(default_factory=dict)
    source_kind: str = "agent_message"
    source_agent: str | None = None
    source_trace_id: str
    source_task_id: str | None = None


class CanonicalCandidate(BaseModel):
    memory_type: MemoryType
    candidate_key: str
    canonical_claim: dict = Field(default_factory=dict)
    similarity: float | None = None


class CandidateSupportCreate(BaseModel):
    support_type: str = Field(default="support", min_length=1)
    source_kind: str | None = None
    source_agent: str | None = None
    task_id: str | None = None
    trace_id: str | None = None
    rag_space_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    evidence_pointer: dict | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    weight: float | None = Field(default=None, ge=0.0, le=1.0)


class CandidateListItem(BaseModel):
    memory_id: str
    memory_type: str
    status: str
    summary: str
    candidate_key: str | None = None
    canonical_claim: dict | None = None
    support_count: int = 0
    negative_count: int = 0
    conflict_count: int = 0
    rag_evidence_count: int = 0
    agent_verifier_count: int = 0
    human_approved: bool = False
    promotion_score: float | None = None
    confidence: float | None = None
    trust_score: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_supported_at: datetime | None = None


class PromotionEvaluationResponse(BaseModel):
    memory_id: str
    status: MemoryStatus
    promotion_score: float
    promoted: bool = False
    reason: str | None = None
    blocked_reasons: list[str] = Field(default_factory=list)


# ---- Search / Retrieval ----

class ScopeFilter(BaseModel):
    memory_type: list[MemoryType] | None = None
    product_line: str | None = None
    rag_space_id: str | None = None
    task_id: str | None = None


class MemorySearchRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    user_id: str | None = None
    query: str = Field(..., min_length=1)
    scope_filter: ScopeFilter | None = None
    top_k: int = Field(default=5, ge=1, le=10)
    trace_id: str | None = None


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


class MemoryContext(BaseModel):
    items: list[MemorySearchItem] = Field(default_factory=list)


class MemorySearchResponse(BaseModel):
    memory_context: MemoryContext
    items: list[MemorySearchItem] = Field(default_factory=list)
    policy_version: str = "default:v1"
    trace_id: str | None = None
    conflict_info: dict | None = None


class MemoryErrorDetail(BaseModel):
    error_code: str
    message: str
    trace_id: str | None = None


class MemoryErrorResponse(BaseModel):
    detail: MemoryErrorDetail


# ---- Conflict Detection & Arbitration ----

class ConflictRelation(str, Enum):
    CONTRADICTS = "contradicts"
    UNRELATED = "unrelated"


class ConflictItem(BaseModel):
    memory_id: str
    summary: str
    memory_type: str
    confidence: float | None = None
    trust_score: float | None = None


class ConflictDetail(BaseModel):
    edge_id: str
    source_memory: ConflictItem
    target_memory: ConflictItem
    relation: ConflictRelation
    created_at: str | None = None


class ConflictListResponse(BaseModel):
    conflicts: list[ConflictDetail] = Field(default_factory=list)
    total: int = 0


class ConflictResolveRequest(BaseModel):
    action: str = Field(..., description="keep_A / keep_B / merge / dismiss")
    reviewer_id: str = Field(..., min_length=1)
    comment: str | None = None


class ConflictResolveResponse(BaseModel):
    resolution: str
    source_memory_status: str
    target_memory_status: str
    merged_memory_id: str | None = None


# ---- Events ----

class MemoryEventPayload(BaseModel):
    event_id: str = Field(..., min_length=1)
    org_id: str = Field(..., min_length=1)
    user_id: str | None = None
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
    parent_event_ids: dict | None = None


# ---- Propagation ----

class MemoryPropagationRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    root_memory_id: str = Field(..., min_length=1)
    trace_id: str | None = None
    max_depth: int = Field(default=4, ge=1, le=10)
    include_edge_types: list[EdgeType] = Field(default_factory=lambda: [
        EdgeType.VERSION_OF,
        EdgeType.SUMMARIZED_FROM,
        EdgeType.MERGED_FROM,
        EdgeType.DERIVED_FROM,
        EdgeType.CITED_AS_EVIDENCE,
        EdgeType.PLANNED_FROM,
        EdgeType.ROLLBACK_DEPENDS_ON,
    ])


class PropagationNode(BaseModel):
    memory_id: str
    classification: str  # direct_contaminated / indirect_contaminated / suspected / clean_boundary
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
    approval_id: str | None = None
    before_snapshot: dict | None = None
    after_snapshot: dict | None = None


# ---- Evaluation ----

class MemoryEvaluationRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    rollback_id: str
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

class MemoryPolicyUpsert(BaseModel):
    policy_type: PolicyType
    config: dict = Field(..., min_length=1)
    status: str = "active"


class MemoryPolicyResponse(BaseModel):
    policy_key: str
    policy_type: str
    config: dict | None = None
    status: str
    version: int
    updated_at: datetime | None = None


# ---- Retrieval Conflict Guard ----

class ConflictGuardInput(BaseModel):
    query: str = Field(..., min_length=1)
    rag_hits: list[dict] = Field(default_factory=list)
    memory_hits: list[dict] = Field(default_factory=list)
    session_facts: dict | None = None
    tool_results: list[dict] | None = None


class ConflictGuardOutput(BaseModel):
    rag_hits: list[dict] = Field(default_factory=list)
    memory_hits: list[dict] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    suppressed_memory_ids: list[str] = Field(default_factory=list)
    downranked_memory_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConflictCheckInput(BaseModel):
    query: str = Field(..., min_length=1)
    memory_id: str = Field(..., min_length=1)
    memory_summary: str = Field(..., min_length=1)
    rag_hits: list[dict] = Field(default_factory=list)
    session_facts: dict | None = None


class ConflictCheckOutput(BaseModel):
    memory_id: str
    verdict: str  # support | conflict | refine | unrelated | uncertain
    confidence: float
    reason: str | None = None
    conflicts: list[dict] = Field(default_factory=list)


class SearchWithConflictGuardRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    user_id: str | None = None
    query: str = Field(..., min_length=1)
    rag_space_id: str | None = None
    scope_filter: ScopeFilter | None = None
    top_k_memory: int = Field(default=5, ge=1, le=10)
    top_k_rag: int = Field(default=3, ge=1, le=10)
    enable_conflict_guard: bool = True
    session_facts: dict | None = None
    tool_results: list[dict] | None = None
    trace_id: str | None = None


class SearchWithConflictGuardResponse(BaseModel):
    rag_hits: list[dict] = Field(default_factory=list)
    memory_hits: list[dict] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    suppressed_memory_ids: list[str] = Field(default_factory=list)
    downranked_memory_ids: list[str] = Field(default_factory=list)
    policy: dict = Field(default_factory=dict)
    trace_id: str | None = None
