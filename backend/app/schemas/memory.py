from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


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
    REJECTED = "rejected"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"
    ISOLATED = "isolated"
    DISABLED = "disabled"
    DELETED = "deleted"
    EXPIRED = "expired"


class UsagePolicy(str, Enum):
    CONTEXT_ONLY = "context_only"


class PrivacyLevel(str, Enum):
    TENANT_PRIVATE = "tenant_private"


class MemoryScopeType(str, Enum):
    MEETING_ROOM = "meeting_room"
    INSPECTION_TASK = "inspection_task"
    PRODUCT = "product"
    STANDARD = "standard"
    RAG_SPACE = "rag_space"
    USER = "user"
    ROLE = "role"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
    BATCH = "batch"


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


class MemoryContent(BaseModel):
    summary: str = Field(..., min_length=1, description="Structured summary")
    facts: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class MemoryScope(BaseModel):
    scope_type: MemoryScopeType | None = None
    scope_id: str | None = None
    room_id: str | None = None
    task_id: str | None = None
    product_id: str | None = None
    product_line: str | None = None
    spec_code: str | None = None
    standard_id: str | None = None
    rag_space_id: str | None = None
    user_id: str | None = None
    role: str | None = None
    workspace: str | None = None
    organization_id: str | None = None
    batch_no: str | None = None

    def has_business_scope(self) -> bool:
        return any(
            [
                self.scope_type and self.scope_id,
                self.room_id,
                self.task_id,
                self.product_id,
                self.product_line,
                self.spec_code,
                self.standard_id,
                self.rag_space_id,
                self.user_id,
                self.role,
                self.workspace,
                self.organization_id,
                self.batch_no,
            ]
        )

    def primary_pair(self) -> tuple[str, str] | None:
        if self.scope_type and self.scope_id:
            return self.scope_type.value, self.scope_id
        if self.room_id:
            return MemoryScopeType.MEETING_ROOM.value, self.room_id
        if self.task_id:
            return MemoryScopeType.INSPECTION_TASK.value, self.task_id
        if self.product_id:
            return MemoryScopeType.PRODUCT.value, self.product_id
        if self.product_line:
            return MemoryScopeType.PRODUCT.value, self.product_line
        if self.spec_code:
            return MemoryScopeType.STANDARD.value, self.spec_code
        if self.standard_id:
            return MemoryScopeType.STANDARD.value, self.standard_id
        if self.rag_space_id:
            return MemoryScopeType.RAG_SPACE.value, self.rag_space_id
        if self.user_id:
            return MemoryScopeType.USER.value, self.user_id
        if self.role:
            return MemoryScopeType.ROLE.value, self.role
        if self.workspace:
            return MemoryScopeType.WORKSPACE.value, self.workspace
        if self.organization_id:
            return MemoryScopeType.ORGANIZATION.value, self.organization_id
        if self.batch_no:
            return MemoryScopeType.BATCH.value, self.batch_no
        return None


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
            has_task_scope = (
                self.scope
                and (
                    self.scope.task_id
                    or (
                        self.scope.scope_type == MemoryScopeType.INSPECTION_TASK
                        and self.scope.scope_id
                    )
                )
            )
            if not has_task_scope:
                if not self.source.task_id:
                    raise ValueError("task_episode requires task_id in scope or source")
        if self.memory_type == MemoryType.INSPECTION_PATTERN:
            has_product_scope = (
                self.scope
                and (
                    self.scope.product_line
                    or self.scope.product_id
                    or (
                        self.scope.scope_type == MemoryScopeType.PRODUCT
                        and self.scope.scope_id
                    )
                )
            )
            if not has_product_scope:
                raise ValueError("inspection_pattern requires product_id/product_line in scope")
        if self.memory_type == MemoryType.RAG_USAGE_MEMORY:
            has_rag_scope = (
                self.scope
                and (
                    self.scope.rag_space_id
                    or (
                        self.scope.scope_type == MemoryScopeType.RAG_SPACE
                        and self.scope.scope_id
                    )
                )
            )
            if not has_rag_scope:
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


# ---- Search / Retrieval ----

class ScopeFilter(BaseModel):
    memory_type: list[MemoryType] | None = None
    scope_type: list[MemoryScopeType] | None = None
    room_id: str | None = None
    product_id: str | None = None
    product_line: str | None = None
    spec_code: str | None = None
    standard_id: str | None = None
    rag_space_id: str | None = None
    user_id: str | None = None
    task_id: str | None = None
    role: str | None = None
    workspace: str | None = None
    organization_id: str | None = None
    batch_no: str | None = None


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


class MemoryContext(BaseModel):
    items: list[MemorySearchItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    degraded: bool = False


class MemorySearchResponse(BaseModel):
    memory_context: MemoryContext = Field(default_factory=MemoryContext)
    items: list[MemorySearchItem] = Field(default_factory=list)
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_memory_context(self) -> MemorySearchResponse:
        if not self.memory_context.items and self.items:
            self.memory_context.items = list(self.items)
        if not self.memory_context.warnings and self.warnings:
            self.memory_context.warnings = list(self.warnings)
        self.memory_context.degraded = self.degraded
        return self


class RetrievalGatewayScope(BaseModel):
    room_id: str | None = None
    task_id: str | None = None
    product_id: str | None = None
    product_line: str | None = None
    spec_code: str | None = None
    standard_id: str | None = None
    rag_space_id: str | None = None
    user_id: str | None = None
    role: str | None = None
    workspace: str | None = None
    organization_id: str | None = None
    batch_no: str | None = None
    scope_node_ids: list[str] = Field(default_factory=list)


class RetrievalGatewayRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    user_id: str | None = None
    workspace: Workspace = Workspace.APP
    query: str = Field(..., min_length=1)
    scope: RetrievalGatewayScope = Field(default_factory=RetrievalGatewayScope)
    memory_type: list[MemoryType] | None = None
    include_documents: bool = True
    include_memory: bool = True
    top_k: int = Field(default=5, ge=1, le=10)


class RetrievalGatewayResponse(BaseModel):
    query: str
    document_evidence: list[dict] = Field(default_factory=list)
    memory_evidence: list[MemorySearchItem] = Field(default_factory=list)
    document_rag: dict | None = None
    memory_context: MemoryContext = Field(default_factory=MemoryContext)
    conflicts: list[dict] = Field(default_factory=list)
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)


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
    parent_event_ids: dict | None = None


# ---- Propagation ----

class MemoryPropagationRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    workspace: str = Field(default="governance")
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
    approval_id: str | None = None
    before_snapshot: dict | None = None
    after_snapshot: dict | None = None


# ---- Evaluation ----

class MemoryEvaluationRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    workspace: str = Field(default="governance")
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
    workspace: Workspace
    policy_type: PolicyType
    config: dict = Field(..., min_length=1)
    status: str = "active"


class MemoryPolicyResponse(BaseModel):
    policy_key: str
    policy_type: str
    workspace: Workspace
    config: dict | None = None
    status: str
    version: int
    updated_at: datetime | None = None
