from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.qdl import QDLDocument


class MeetingRoomCreateRequest(BaseModel):
    title: str = Field(default="会议室", min_length=1, max_length=120)
    password: str | None = Field(default=None, max_length=64)
    visibility: str = Field(default="private", pattern="^(private|team|org|restricted)$")
    allowed_data_domains: list[str] | None = None
    business_context: dict | None = None
    auto_participation_mode: str = Field(default="off", pattern="^(off|live)$")


class MeetingRoomJoinRequest(BaseModel):
    access_code: str = Field(..., min_length=4, max_length=16)
    password: str | None = Field(default=None, max_length=64)


class MeetingMessageCreateRequest(BaseModel):
    content: str = Field(default="", max_length=4000)
    quote_message_id: str | None = None
    private_recipient_user_id: str | None = None
    skip_agent_trigger: bool = False
    attachments: list[dict] = Field(default_factory=list)
    quote_snapshot: dict | None = None


class MeetingMessageUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class MeetingRoomUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    visibility: str | None = Field(default=None, pattern="^(private|team|org|restricted)$")
    allowed_data_domains: list[str] | None = None
    business_context: dict | None = None
    auto_participation_mode: str | None = Field(default=None, pattern="^(off|live)$")


class MeetingBusinessContextTask(BaseModel):
    id: str
    product_id: str = ""
    spec_code: str = ""
    status: str = ""
    priority: int | None = None
    has_result: bool = False
    has_stability: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MeetingBusinessContext(BaseModel):
    task_ids: list[str] = []
    product_ids: list[str] = []
    batch_nos: list[str] = []
    standard_ids: list[str] = []
    tasks: list[MeetingBusinessContextTask] = []


class MeetingRoomResponse(BaseModel):
    id: str
    org_id: str
    title: str
    access_code: str
    created_by: str
    status: str
    visibility: str = "private"
    allowed_data_domains: list[str] = []
    memory_policy: dict | None = None
    audit_policy: dict | None = None
    business_context: MeetingBusinessContext = Field(default_factory=MeetingBusinessContext)
    member_count: int = 0
    agent_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MeetingMessageResponse(BaseModel):
    id: str
    room_id: str
    user_id: str
    username: str
    seq_no: int
    content: str
    message_type: str = "user"
    agent_id: str | None = None
    mentions: list[dict] | None = None
    quote_message_id: str | None = None
    metadata_json: dict | None = None
    private_recipient_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MeetingDiscussionStartResponse(BaseModel):
    started: bool
    participant_count: int = 0
    topic_message: MeetingMessageResponse | None = None


# ── Agent schemas ────────────────────────────────────────────────

class MeetingAddAgentRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    role: str = Field(default="participant", pattern="^(participant|observer)$")
    allowed_domains: list[str] | None = None
    allowed_tools: list[str] | None = None


class MeetingRoomAgentResponse(BaseModel):
    id: str
    room_id: str
    agent_id: str
    agent_name: str = ""
    role: str
    added_by: str
    allowed_domains: list[str] = []
    allowed_tools: list[str] = []

    model_config = {"from_attributes": True}


class MeetingRoomMemberResponse(BaseModel):
    id: str
    room_id: str
    user_id: str
    username: str = ""
    role: str = "member"
    joined_at: datetime | None = None


class MeetingMemberRoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern="^(host|member)$")


class MeetingRoomDetailResponse(MeetingRoomResponse):
    agents: list[MeetingRoomAgentResponse] = []
    members: list[MeetingRoomMemberResponse] = []


class MeetingContextPreviewResponse(BaseModel):
    room_id: str
    user_role: str
    room_role: str
    allowed_domains: list[str] = []
    denied_domains: list[str] = []
    effective_domains: list[str] = []
    room_configured_domains: list[str] = []
    sensitive_domains: list[str] = []
    denied_reasons: dict[str, str] = Field(default_factory=dict)
    agent_permissions: list[dict] = []
    query_examples: list[str] = []
    guardrails: list[str] = []
    business_context: MeetingBusinessContext = Field(default_factory=MeetingBusinessContext)
    share_policy: dict = Field(default_factory=dict)
    conflict_rules: dict = Field(default_factory=dict)
    visibility_rules: dict = Field(default_factory=dict)


class MeetingBusinessContextUpdateRequest(BaseModel):
    task_ids: list[str] = Field(default_factory=list, max_length=20)
    product_ids: list[str] = Field(default_factory=list, max_length=20)
    batch_nos: list[str] = Field(default_factory=list, max_length=20)
    standard_ids: list[str] = Field(default_factory=list, max_length=20)


class MeetingBusinessObjectCandidateResponse(BaseModel):
    id: str
    room_id: str
    object_type: str
    object_value: str
    resolved_value: str | None = None
    status: str
    confidence: float | None = None
    source_message_ids: list[str] = []
    evidence_json: dict | None = None
    created_by: str | None = None
    resolved_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MeetingBusinessObjectCorrectionRequest(BaseModel):
    correction: str = Field(..., min_length=1, max_length=500)
    candidate_id: str | None = Field(default=None, max_length=64)
    action: str = Field(default="correct", pattern="^(correct|reject)$")
    object_type: str | None = Field(
        default=None,
        pattern="^(task|product|batch|standard|unknown)$",
    )
    corrected_value: str | None = Field(default=None, max_length=128)


class MeetingAgentQueryAuditResponse(BaseModel):
    id: str
    room_id: str
    user_id: str
    agent_id: str
    question: str
    intent: str | None = None
    requested_domains: list[str] = []
    allowed_domains: list[str] = []
    denied_domains: list[str] = []
    tool_calls: list[dict] = []
    source_refs: list[dict] = []
    memory_reads: list[dict] = []
    redacted_fields: list[str] = []
    decision: str = "allowed"
    response_visibility: str = "room"
    redaction_level: str = "none"
    denied_reasons: dict[str, str] = Field(default_factory=dict)
    conflict_ref_id: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class MeetingMemoryScopeRequest(BaseModel):
    include_meeting: bool = True
    include_confirmed: bool = True
    include_personal_authorized: bool = False
    include_user: bool = False
    include_agent: bool = True
    include_org_space: bool = True


class MeetingAgentRunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    mode: str = Field(default="auto", pattern="^(auto|risk_forecast|evidence_query|standard_explain|meeting_summary|memory_transfer|action_items)$")
    memory_scope: MeetingMemoryScopeRequest = Field(default_factory=MeetingMemoryScopeRequest)
    attachments: list[dict] = Field(default_factory=list)
    workflow_run_id: str | None = None
    replace_message_id: str | None = None
    interaction_mode: str = Field(
        default="private_chat",
        pattern="^(private_chat|public_mention|auto_participation)$",
    )
    question_message_id: str | None = Field(default=None, max_length=64)
    trigger_message_id: str | None = Field(default=None, max_length=64)
    question_revision: str | None = Field(default=None, max_length=128)
    question_sources: list[dict] = Field(default_factory=list, max_length=20)
    auto_participation: dict | None = Field(default=None, exclude=True)


class MeetingAgentShareRequest(BaseModel):
    answer_message_id: str = Field(..., min_length=1, max_length=64)
    content: str = Field(..., min_length=1, max_length=4000)
    source_message_ids: list[str] = Field(default_factory=list, max_length=20)


class MeetingMemorySourceResponse(BaseModel):
    memory_id: str
    scope: str = "meeting_room"
    title: str = ""
    summary: str = ""


class MeetingCandidateMemoryResponse(BaseModel):
    memory_id: str
    title: str
    content: str
    summary: str = ""
    memory_type: str = "decision"
    status: str = "candidate"
    memory_category: str = "meeting_memory"
    recommended_scope: str = "meeting_room"
    recommended_scope_id: str | None = None
    source_refs: list[dict] = []
    business_context: dict | None = None
    shareability: dict | None = None
    warnings: list[str] = []
    affected_objects: dict | None = None
    evidence_refs: list[dict] = []
    forecast_window: dict | None = None
    risk_level: str | None = None
    recommended_actions: list[str] = []
    source_room_id: str | None = None
    source_spans: list[dict] = []
    object_resolution_status: str = "unresolved"
    object_candidates: list[dict] = []
    value_score: float | None = None
    dedupe_key: str | None = None
    related_memory_ids: list[str] = []
    discussion_relations: list[dict] = []
    extraction_reason: str | None = None
    confidence: float | None = None
    source_message_id: str | None = None
    qdl_json: QDLDocument | None = None
    qdl_schema_version: str | None = None
    qdl_validation_status: str = "missing"
    qdl_validation_errors: list[str] = []
    extraction_method: str | None = None
    extraction_model_id: str | None = None
    extraction_metrics: dict | None = None
    created_at: datetime | None = None


class MeetingAgentRunResponse(BaseModel):
    selected_subgraph: str
    answer: str
    message: MeetingMessageResponse
    memory_sources: list[MeetingMemorySourceResponse] = []
    candidate_memories: list[MeetingCandidateMemoryResponse] = []
    response_visibility: str = "room"
    escalation_required: bool = False
    conflict_status: str | None = None
    conflict_ref_id: str | None = None
    trust_protocol: dict = {}


class MeetingMemoryExtractRequest(BaseModel):
    topic: str | None = Field(default=None, max_length=200)
    max_items: int = Field(default=3, ge=1, le=10)


class MeetingMemoryResponse(BaseModel):
    memory_id: str
    title: str
    content: str
    summary: str = ""
    memory_type: str
    status: str
    review_status: str = "candidate"
    readiness_status: str = "collecting"
    scope: str = "meeting_room"
    scope_type: str | None = None
    scope_id: str | None = None
    requested_scope_type: str | None = None
    requested_scope_id: str | None = None
    pending_transfer_id: str | None = None
    shared_scopes: list[dict] = []
    pending_share_requests: list[dict] = []
    applicability: dict = {}
    evidence_summary: dict = {}
    memory_category: str = "meeting_memory"
    recommended_scope: str | None = None
    recommended_scope_id: str | None = None
    source_refs: list[dict] = []
    business_context: dict | None = None
    shareability: dict | None = None
    warnings: list[str] = []
    affected_objects: dict | None = None
    evidence_refs: list[dict] = []
    forecast_window: dict | None = None
    risk_level: str | None = None
    recommended_actions: list[str] = []
    source_room_id: str | None = None
    source_spans: list[dict] = []
    object_resolution_status: str | None = None
    object_candidates: list[dict] = []
    value_score: float | None = None
    dedupe_key: str | None = None
    related_memory_ids: list[str] = []
    discussion_relations: list[dict] = []
    extraction_reason: str | None = None
    publish_reason: str | None = None
    version_parent_id: str | None = None
    confidence: float | None = None
    source_message_id: str | None = None
    qdl_json: QDLDocument | None = None
    qdl_schema_version: str | None = None
    qdl_validation_status: str = "missing"
    qdl_validation_errors: list[str] = []
    extraction_method: str | None = None
    extraction_model_id: str | None = None
    extraction_metrics: dict | None = None
    created_by: str | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MeetingMemoryUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    scope: str = Field(default="meeting_room", pattern="^(meeting|meeting_room|collab_thread|user|agent|org_space|workspace|organization)$")
    scope_id: str | None = Field(default=None, min_length=1, max_length=128)
    publish_reason: str | None = Field(default=None, max_length=1000)
    is_business_memory: bool | None = None
    affected_objects: dict | None = None
    object_resolution_status: str | None = Field(default=None, pattern="^(resolved|ambiguous|unresolved)$")
    related_memory_ids: list[str] | None = None


class MeetingMemoryDisputeRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)
    conflicting_memory_id: str | None = Field(default=None, min_length=1, max_length=64)


class MeetingMemoryTransferRequest(BaseModel):
    to_scope_type: str = Field(default="meeting_room", pattern="^(meeting|meeting_room|collab_thread|user|agent|org_space|workspace|organization)$")
    to_scope_id: str = Field(default="current", min_length=1, max_length=128)
    transfer_reason: str | None = Field(default=None, max_length=1000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class MeetingMemoryShareRequest(BaseModel):
    target_scope_type: str = Field(default="meeting_room", pattern="^(meeting|meeting_room|collab_thread|user|agent|org_space|workspace|organization)$")
    target_scope_id: str = Field(default="current", min_length=1, max_length=128)
    share_reason: str | None = Field(default=None, max_length=1000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class MeetingMemoryShareCreateRequest(MeetingMemoryShareRequest):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    affected_objects: dict | None = None
    related_memory_ids: list[str] | None = None
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    mapping_rules: dict = Field(default_factory=dict)
    mapping_version: str = Field(default="manual-v1", min_length=1, max_length=128)
    interpolation_strategy: Literal["explicit", "identity", "drop_unmapped"] = "explicit"


class MeetingMemoryShareDecisionRequest(BaseModel):
    decision_note: str | None = Field(default=None, max_length=1000)


class MeetingMemoryShareRejectRequest(BaseModel):
    decision_note: str = Field(..., min_length=1, max_length=1000)


class MeetingConflictEventResponse(BaseModel):
    id: str
    room_id: str
    conflict_type: str
    resource_key: str
    status: str
    initiator_user_id: str
    workflow_run_id: str | None = None
    related_message_ids: list[str] = []
    candidate_actions: list[dict] = []
    selected_action: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    metadata_json: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MeetingConflictResolveRequest(BaseModel):
    selected_action: str = Field(..., pattern="^(approve|queue|reject|candidate_only)$")


class MeetingMemoryShareApprovalResponse(BaseModel):
    id: str
    memory_id: str
    from_scope_type: str
    from_scope_id: str
    to_scope_type: str
    to_scope_id: str
    transfer_reason: str | None = None
    status: str
    operator_id: str | None = None
    requested_by: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    idempotency_key: str | None = None
    mapping_plan: dict | None = None
    mapping_version: str | None = None
    interpolation_strategy: str | None = None
    unmapped_fields: list[str] = []
    memory_title: str = ""
    memory_content: str = ""
    source_refs: list[dict] = []
    affected_objects: dict | None = None
    source_room_id: str | None = None
    can_approve: bool = False
    can_cancel: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MeetingMemoryShareCreateResponse(BaseModel):
    memory: MeetingMemoryResponse
    share_request: MeetingMemoryShareApprovalResponse


class MeetingActionItemCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    owner_id: str | None = None
    due_at: datetime | None = None
    source_message_id: str | None = None


class MeetingActionItemUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    owner_id: str | None = None
    due_at: datetime | None = None
    status: str | None = Field(default=None, pattern="^(open|in_progress|done|cancelled)$")


class MeetingActionItemResponse(BaseModel):
    id: str
    room_id: str
    title: str
    description: str | None = None
    owner_id: str | None = None
    owner_name: str = ""
    due_at: datetime | None = None
    status: str = "open"
    source_message_id: str | None = None
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Admin schemas ────────────────────────────────────────────────

class AdminMeetingRoomResponse(MeetingRoomResponse):
    created_by_username: str = ""
    message_count: int = 0


class AdminMeetingRoomQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)
    keyword: str | None = None
    status: str | None = None


# ── Agent Definition schemas ──────────────────────────────────────

class AgentDefinitionResponse(BaseModel):
    id: str
    org_id: str
    name: str
    system_prompt: str
    model: str = "deepseek-chat"
    adapter_type: str = "llm"
    participation_strategy: dict | None = None
    is_active: bool = True
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentDefinitionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    system_prompt: str = Field(..., min_length=1, max_length=5000)
    model: str = Field(default="deepseek-chat", max_length=64)
    adapter_type: str = Field(
        default="llm",
        description="llm 或已由部署开关启用的 pipeline。",
    )
    participation_strategy: dict | None = None

    @field_validator("adapter_type")
    @classmethod
    def validate_adapter_type(cls, value: str) -> str:
        from agent.adapters.factory import AgentAdapterFactory

        try:
            return AgentAdapterFactory.ensure_supported(value)
        except Exception as exc:
            raise ValueError(str(getattr(exc, "message", None) or exc)) from exc


class AgentDefinitionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=5000)
    model: str | None = Field(default=None, max_length=64)
    participation_strategy: dict | None = None
    is_active: bool | None = None
