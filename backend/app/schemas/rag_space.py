from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RagSpaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class RagSpaceFileResponse(BaseModel):
    id: str
    rag_space_id: str
    org_id: str
    file_name: str
    content_type: str | None = None
    file_url: str
    size_bytes: int
    status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RagSpaceResponse(BaseModel):
    id: str
    org_id: str
    created_by: str | None = None
    name: str
    description: str | None = None
    status: str
    file_count: int
    selected_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    files: list[RagSpaceFileResponse] = []

    model_config = {"from_attributes": True}


class ChatAttachmentPayload(BaseModel):
    id: str
    name: str
    url: str
    content_type: str | None = None
    size_bytes: int = 0
    kind: str = "file"


class AttachmentUploadResponse(BaseModel):
    items: list[ChatAttachmentPayload]
