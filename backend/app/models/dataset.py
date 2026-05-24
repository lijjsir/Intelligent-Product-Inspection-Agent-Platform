from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary, TimestampMixin


class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("org_id", "created_by", "name", name="uq_datasets_owner_name"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    modality: Mapped[str] = mapped_column(String(32), nullable=False, default="image_text")
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    video_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    knowledge_graph_status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    alignment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    augmentation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")


class DatasetSample(Base, TimestampMixin):
    __tablename__ = "dataset_samples"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    sample_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    sample_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    storage_backend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bucket: Mapped[str | None] = mapped_column(String(120), nullable=True)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    annotation_data: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    related_entities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    preview_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_augmented: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    augmentation_source_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    augmentation_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    augmentation_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DatasetAsyncJob(Base, TimestampMixin):
    __tablename__ = "dataset_async_jobs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, default="upload_summary")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class DatasetUploadSession(Base, TimestampMixin):
    __tablename__ = "dataset_upload_sessions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    dataset_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bucket: Mapped[str | None] = mapped_column(String(120), nullable=True)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_parts_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
