from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MeetingRoomCreateRequest(BaseModel):
    title: str = Field(default="会议室", min_length=1, max_length=120)
    password: str | None = Field(default=None, max_length=64)
    room_type: str = Field(
        default="quality_business",
        pattern="^(quality_business|platform_ops|org_admin|data_ops|memory_governance|general)$",
    )
    visibility: str = Field(default="private", pattern="^(private|team|org|restricted)$")
    allowed_data_domains: list[str] | None = None


class MeetingRoomJoinRequest(BaseModel):
    access_code: str = Field(..., min_length=4, max_length=16)
    password: str | None = Field(default=None, max_length=64)


class MeetingMessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    quote_message_id: str | None = None
    skip_agent_trigger: bool = False


class MeetingRoomUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    room_type: str | None = Field(
        default=None,
        pattern="^(quality_business|platform_ops|org_admin|data_ops|memory_governance|general)$",
    )
    visibility: str | None = Field(default=None, pattern="^(private|team|org|restricted)$")
    allowed_data_domains: list[str] | None = None


class MeetingRoomResponse(BaseModel):
    id: str
    org_id: str
    title: str
    access_code: str
    created_by: str
    status: str
    room_type: str = "quality_business"
    visibility: str = "private"
    allowed_data_domains: list[str] = []
    memory_policy: dict | None = None
    audit_policy: dict | None = None
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
    room_type: str
    room_type_label: str
    user_role: str
    room_role: str
    allowed_domains: list[str] = []
    denied_domains: list[str] = []
    agent_permissions: list[dict] = []
    query_examples: list[str] = []
    guardrails: list[str] = []


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
    redacted_fields: list[str] = []
    decision: str = "allowed"
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class MeetingMemoryScopeRequest(BaseModel):
    include_meeting: bool = True
    include_project_shared: bool = True
    include_personal_authorized: bool = False


class MeetingAgentRunRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    mode: str = Field(default="auto", pattern="^(auto|risk_forecast|evidence_query|standard_explain|meeting_summary|memory_transfer|action_items)$")
    memory_scope: MeetingMemoryScopeRequest = Field(default_factory=MeetingMemoryScopeRequest)


class MeetingMemorySourceResponse(BaseModel):
    memory_id: str
    scope: str = "project_shared"
    title: str = ""
    summary: str = ""


class MeetingCandidateMemoryResponse(BaseModel):
    memory_id: str
    title: str
    content: str
    summary: str = ""
    memory_type: str = "decision"
    status: str = "candidate"
    recommended_scope: str = "project_shared"
    confidence: float | None = None
    source_message_id: str | None = None
    created_at: datetime | None = None


class MeetingAgentRunResponse(BaseModel):
    selected_subgraph: str
    answer: str
    message: MeetingMessageResponse
    memory_sources: list[MeetingMemorySourceResponse] = []
    candidate_memories: list[MeetingCandidateMemoryResponse] = []


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
    scope: str = "meeting"
    confidence: float | None = None
    source_message_id: str | None = None
    created_by: str | None = None
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MeetingMemoryUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    scope: str = Field(default="project_shared", pattern="^(meeting|project_shared)$")


class MeetingMemoryTransferRequest(BaseModel):
    to_scope_type: str = Field(default="project", pattern="^(user|meeting_room|project|org)$")
    to_scope_id: str = Field(default="default", min_length=1, max_length=128)
    transfer_reason: str | None = Field(default=None, max_length=1000)


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
    adapter_type: str = Field(default="llm", pattern="^(llm|pipeline)$")
    participation_strategy: dict | None = None


class AgentDefinitionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=5000)
    model: str | None = Field(default=None, max_length=64)
    participation_strategy: dict | None = None
    is_active: bool | None = None
