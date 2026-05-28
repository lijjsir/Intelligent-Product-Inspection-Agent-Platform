from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import PageParams


class ImageItem(BaseModel):
    """Per-image metadata for traceability and duplicate detection."""
    index: int = Field(ge=0, description="Zero-based position in the image list")
    url: str = Field(min_length=1)
    hash: str = Field(min_length=1, description="SHA-256 hex digest of the image content")
    sample_number: int | None = Field(default=None, ge=1, description="Batch sample/unit number for traceability")

    @classmethod
    def from_url(cls, index: int, url: str, content_bytes: bytes | None = None) -> ImageItem:
        """Build an ImageItem, computing hash from raw bytes when available;
        otherwise fall back to hashing the URL string."""
        if content_bytes:
            digest = hashlib.sha256(content_bytes).hexdigest()
        else:
            digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return cls(index=index, url=url, hash=digest)


class TaskListQuery(PageParams):
    status: Optional[str] = None
    product_id: Optional[str] = None
    ids: Optional[str] = None

    def to_filters(self) -> dict:
        data = {k: v for k, v in self.model_dump(exclude={"page", "size"}).items() if v is not None}
        if data.get("ids"):
            data["ids"] = [item.strip() for item in data["ids"].split(",") if item.strip()]
        return data


class TaskCreate(BaseModel):
    product_id: str
    spec_code: str
    image_urls: List[str]
    image_items: Optional[List[ImageItem]] = None
    priority: int = Field(default=5, ge=1, le=10)
    metadata: Optional[dict] = None

    @field_validator("image_items")
    @classmethod
    def validate_image_items(cls, v: list[ImageItem] | None, info) -> list[ImageItem] | None:
        if v is None:
            return None
        indices = [item.index for item in v]
        if sorted(indices) != list(range(len(v))):
            raise ValueError("image_items 的 index 必须从 0 开始连续递增")
        return v

    def deduplicated_items(self) -> list[ImageItem]:
        """Return image_items with duplicates removed, keeping first occurrence."""
        if not self.image_items:
            return [
                ImageItem.from_url(i, url)
                for i, url in enumerate(self.image_urls)
            ]
        seen: set[str] = set()
        result: list[ImageItem] = []
        for item in self.image_items:
            if item.hash not in seen:
                seen.add(item.hash)
                result.append(item)
        return result


class TaskResponse(BaseModel):
    id: str
    org_id: str
    org_slug: str | None = None
    created_by: str
    product_id: str
    spec_code: str
    status: str
    priority: int
    image_urls: List[str]
    image_items: Optional[List[ImageItem]] = None
    source_kind: str | None = None
    source_graph: str | None = None
    has_result: bool = False
    has_stability: bool = False
    result_id: str | None = None
    stability_id: str | None = None
    execution: dict[str, Any] | None = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskListItemResponse(BaseModel):
    id: str
    org_id: str
    org_slug: str | None = None
    created_by: str
    product_id: str
    spec_code: str
    status: str
    priority: int
    source_kind: str | None = None
    source_graph: str | None = None
    has_result: bool = False
    has_stability: bool = False
    result_id: str | None = None
    stability_id: str | None = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskStatusResponse(BaseModel):
    id: str
    status: str

    model_config = {"from_attributes": True}


class TaskExecutionEventResponse(BaseModel):
    id: str
    task_id: str
    event_type: str
    stage: str | None = None
    status: str | None = None
    message: str | None = None
    payload_json: dict[str, Any] | None = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


TaskResultIngestTarget = Literal["rag", "dataset", "both"]
TaskResultIngestMode = Literal["candidate"]


class TaskResultIngestRequest(BaseModel):
    target: TaskResultIngestTarget
    rag_space_id: str | None = None
    dataset_id: str | None = None
    dataset_name: str | None = None
    mode: TaskResultIngestMode = "candidate"

    @staticmethod
    def _normalize_uuid(value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        if not cleaned:
            return None
        try:
            return str(uuid.UUID(cleaned))
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid UUID") from exc

    @model_validator(mode="after")
    def validate_target_ids(self) -> "TaskResultIngestRequest":
        self.rag_space_id = self._normalize_uuid(self.rag_space_id, "rag_space_id")
        if self.dataset_id is not None:
            self.dataset_id = self._normalize_uuid(self.dataset_id, "dataset_id")
        if self.dataset_name is not None:
            self.dataset_name = str(self.dataset_name).strip() or None
        return self


class TaskResultIngestResponse(BaseModel):
    task_id: str
    target: TaskResultIngestTarget
    mode: TaskResultIngestMode = "candidate"
    rag_space_id: str | None = None
    dataset_id: str | None = None
    dataset_name: str | None = None
    created_document_count: int = 0
    created_sample_count: int = 0
    skipped_count: int = 0
    warnings: list[str] = Field(default_factory=list)
