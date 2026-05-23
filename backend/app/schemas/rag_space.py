from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RagSpaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class RagSpaceUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class RagNodeCreateRequest(BaseModel):
    parent_id: str | None = None
    node_type: Literal["folder"] = "folder"
    name: str = Field(..., min_length=1, max_length=255)


class RagNodeUpdateRequest(BaseModel):
    parent_id: str | None = None
    name: str = Field(..., min_length=1, max_length=255)


class RagDocumentResponse(BaseModel):
    id: str
    org_id: str
    rag_space_id: str
    node_id: str
    file_name: str
    content_type: str | None = None
    file_url: str
    size_bytes: int
    checksum_sha256: str
    storage_backend: str
    bucket: str
    object_key: str
    parse_status: str
    index_status: str
    chunk_count: int
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class RagNodeResponse(BaseModel):
    id: str
    org_id: str
    rag_space_id: str
    parent_id: str | None = None
    created_by: str | None = None
    node_type: str
    name: str
    full_path: str
    depth: int
    sort_order: int
    status: str
    children_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    document: RagDocumentResponse | None = None
    children: list["RagNodeResponse"] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RagSpaceDocumentListItem(BaseModel):
    id: str
    rag_space_id: str
    org_id: str
    node_id: str
    file_name: str
    content_type: str | None = None
    file_url: str
    size_bytes: int
    status: str
    created_at: datetime | None = None


class RagSpaceResponse(BaseModel):
    id: str
    org_id: str
    created_by: str | None = None
    name: str
    description: str | None = None
    status: str
    file_count: int
    folder_count: int
    chunk_count: int
    index_status: str
    selected_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChatAttachmentPayload(BaseModel):
    id: str
    name: str
    url: str
    content_type: str | None = None
    size_bytes: int = 0
    kind: str = "file"
    bucket: str | None = None
    object_key: str | None = None


class AttachmentUploadResponse(BaseModel):
    items: list[ChatAttachmentPayload]


RagNodeResponse.model_rebuild()
