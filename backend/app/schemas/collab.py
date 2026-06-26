from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CollabAttachmentPayload(BaseModel):
    id: str
    name: str
    url: str
    content_type: str | None = None
    size_bytes: int = 0
    kind: str = "file"
    bucket: str | None = None
    object_key: str | None = None


class CollabThreadParticipantResponse(BaseModel):
    id: str
    thread_id: str
    participant_type: str
    participant_id: str
    role: str = "participant"
    last_read_message_id: str | None = None
    joined_at: datetime | None = None


class CollabThreadCreateRequest(BaseModel):
    target_type: str = Field(..., pattern="^(user|meeting_room|agent)$")
    target_id: str = Field(..., min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=200)
    source_type: str = Field(default="user", pattern="^(user|meeting_room|agent)$")
    source_id: str | None = Field(default=None, max_length=128)
    metadata_json: dict | None = None


class CollabThreadResponse(BaseModel):
    id: str
    org_id: str
    thread_type: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    title: str
    status: str
    created_by: str
    last_message_at: datetime | None = None
    unread_count: int = 0
    metadata_json: dict | None = None
    participants: list[CollabThreadParticipantResponse] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CollabTargetResponse(BaseModel):
    target_type: str
    target_id: str
    label: str
    description: str | None = None
    group: str | None = None


class CollabMessageCreateRequest(BaseModel):
    content: str = Field(default="", max_length=4000)
    message_type: str = Field(default="text", pattern="^(text|file|image|system|memory_card|action_request)$")
    reply_to_message_id: str | None = None
    attachments: list[CollabAttachmentPayload] = Field(default_factory=list)
    metadata_json: dict | None = None


class CollabMessageReceiptResponse(BaseModel):
    id: str
    message_id: str
    thread_id: str
    recipient_type: str
    recipient_id: str
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    acted_at: datetime | None = None
    action_status: str = "pending"


class FileAssetResponse(BaseModel):
    id: str
    bucket: str
    object_key: str
    url: str
    file_name: str
    mime_type: str | None = None
    size_bytes: int = 0
    checksum: str = ""


class CollabMessageResponse(BaseModel):
    id: str
    org_id: str
    thread_id: str
    sender_type: str
    sender_id: str
    message_type: str
    content: str
    reply_to_message_id: str | None = None
    metadata_json: dict | None = None
    attachments: list[FileAssetResponse] = []
    receipts: list[CollabMessageReceiptResponse] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CollabMessageActionRequest(BaseModel):
    action_status: str = Field(..., pattern="^(accepted|rejected|done)$")


class CollabAttachmentUploadResponse(BaseModel):
    items: list[CollabAttachmentPayload]
