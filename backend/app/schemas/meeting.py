from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MeetingRoomCreateRequest(BaseModel):
    title: str = Field(default="会议室", min_length=1, max_length=120)
    password: str | None = Field(default=None, max_length=64)


class MeetingRoomJoinRequest(BaseModel):
    access_code: str = Field(..., min_length=4, max_length=16)
    password: str | None = Field(default=None, max_length=64)


class MeetingMessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class MeetingRoomResponse(BaseModel):
    id: str
    org_id: str
    title: str
    access_code: str
    created_by: str
    status: str
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


class MeetingRoomAgentResponse(BaseModel):
    id: str
    room_id: str
    agent_id: str
    agent_name: str = ""
    role: str
    added_by: str

    model_config = {"from_attributes": True}


class MeetingRoomMemberResponse(BaseModel):
    id: str
    room_id: str
    user_id: str
    username: str = ""
    role: str = "member"
    joined_at: datetime | None = None


class MeetingRoomDetailResponse(MeetingRoomResponse):
    agents: list[MeetingRoomAgentResponse] = []
    members: list[MeetingRoomMemberResponse] = []


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
