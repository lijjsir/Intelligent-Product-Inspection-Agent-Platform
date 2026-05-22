from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import PagedResponse


DatasetModality = Literal["image", "text", "image_text"]
DatasetStatus = Literal["active", "archived"]
DatasetSampleType = Literal["image", "text"]


class DatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    modality: DatasetModality = "image_text"
    tags: list[str] = Field(default_factory=list, max_length=20)


class DatasetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    modality: DatasetModality | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    status: DatasetStatus | None = None


class DatasetListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
    keyword: str | None = Field(default=None, max_length=255)
    modality: DatasetModality | None = None
    status: DatasetStatus | None = None


class DatasetListItem(BaseModel):
    id: str
    org_id: str
    created_by: str | None = None
    name: str
    description: str | None = None
    modality: DatasetModality
    tags: list[str] = Field(default_factory=list)
    status: str
    sample_count: int
    image_sample_count: int
    text_sample_count: int
    uploaded_bytes: int
    knowledge_graph_status: str
    alignment_status: str
    augmentation_status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetSampleResponse(BaseModel):
    id: str
    org_id: str
    dataset_id: str
    created_by: str | None = None
    sample_type: DatasetSampleType
    sample_name: str | None = None
    text_content: str | None = None
    content_type: str | None = None
    size_bytes: int
    checksum_sha256: str
    storage_backend: str | None = None
    bucket: str | None = None
    object_key: str | None = None
    file_url: str | None = None
    annotation_data: dict | list | None = None
    quality_score: float | None = None
    related_entities: list | None = None
    source_metadata: dict | None = None
    preview_text: str | None = None
    download_url: str | None = None
    is_augmented: bool = False
    augmentation_source_id: str | None = None
    augmentation_method: str | None = None
    augmentation_params: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DatasetDetailResponse(DatasetListItem):
    recent_jobs: list["AsyncJobResponse"] = Field(default_factory=list)
    supported_export_formats: list[str] = Field(default_factory=lambda: ["vlm-json", "coco", "yolo"])


class DatasetSampleCreateRequest(BaseModel):
    sample_name: str | None = Field(default=None, max_length=255)
    text_content: str = Field(..., min_length=1, max_length=20000)
    annotation_data: dict | list | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    related_entities: list[str] | None = None
    source_metadata: dict | None = None

    @field_validator("annotation_data")
    @classmethod
    def _validate_annotation_data(cls, value):
        if value is None or isinstance(value, (dict, list)):
            return value
        raise ValueError("annotation_data must be an object or array")


class AsyncJobResponse(BaseModel):
    id: str
    org_id: str
    dataset_id: str
    created_by: str | None = None
    job_type: str
    status: str
    payload_json: dict | None = None
    result_summary: dict | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DatasetUploadInitRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    content_type: str | None = Field(default=None, max_length=120)
    file_size: int = Field(..., ge=1)
    chunk_size: int = Field(..., ge=1)
    total_chunks: int = Field(..., ge=1)


class DatasetUploadInitResponse(BaseModel):
    session_id: str
    bucket: str
    object_key: str
    chunk_size: int
    total_chunks: int
    expires_at: datetime | None = None


class DatasetUploadPartResponse(BaseModel):
    session_id: str
    part_number: int
    uploaded_parts: list[int] = Field(default_factory=list)
    uploaded_count: int = 0


class DatasetUploadCompleteRequest(BaseModel):
    session_id: str
    uploaded_parts: list[int] = Field(default_factory=list)


class DatasetUploadCompleteResponse(BaseModel):
    session_id: str
    job: AsyncJobResponse
    dataset: DatasetDetailResponse


class DatasetJobResponse(AsyncJobResponse):
    pass


class DatasetListResponse(PagedResponse[DatasetListItem]):
    pass


DatasetDetailResponse.model_rebuild()
