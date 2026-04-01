from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.rag_space import ChatAttachmentPayload


class ChatTaskDraft(BaseModel):
    product_id: str | None = None
    spec_code: str | None = None
    image_urls: list[str] = []
    priority: int | None = None
    metadata: dict[str, Any] = {}


class ChatSelectedRagSpace(BaseModel):
    id: str
    name: str
    description: str | None = None


class ChatCreatedTask(BaseModel):
    id: str
    status: str
    product_id: str
    spec_code: str
    priority: int
    image_count: int


class ChatSessionResponse(BaseModel):
    id: str
    org_id: str
    user_id: str
    title: str | None = None
    status: str
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    seq_no: int
    role: str
    message_type: str
    content: str
    payload: dict[str, Any] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChatSessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ChatMessageSendRequest(BaseModel):
    schema_version: str = "1.0.0"
    workspace: str = "app"
    message: str = Field(..., min_length=1, max_length=4000)
    metadata: dict[str, Any] | None = None
    ext: dict[str, Any] | None = None


class ChatTaskResultAppendRequest(BaseModel):
    task_id: str
    status: str
    product_id: str
    spec_code: str
    priority: int
    image_count: int


class ChatSendResponse(BaseModel):
    session: ChatSessionResponse
    user_message: ChatMessageResponse
    assistant_message_id: str
    workflow_run_id: str


class ChatAssistantPayload(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = []
    quality: dict[str, Any] = {}
    trace_id: str | None = None
    workflow_version: str = "quality_chat_v1"
    prompt_version: str = "builtin-quality-chat-v1"
    intent: str | None = None
    intent_confidence: float | None = None
    action_state: str | None = None
    task_draft: ChatTaskDraft | None = None
    task_form_defaults: ChatTaskDraft | None = None
    task_submit_mode: str | None = None
    missing_slots: list[str] = []
    pending_action: str | None = None
    awaiting_confirmation: bool = False
    created_task: ChatCreatedTask | None = None
    selected_rag_space: ChatSelectedRagSpace | None = None
    attachment_echo: list[ChatAttachmentPayload] = []
    message_type: str | None = None


class ChatStreamEvent(BaseModel):
    event: str
    session_id: str
    message_id: str | None = None
    workflow_run_id: str | None = None
    delta: str | None = None
    content: str | None = None
    quality: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    ts: str | None = None
