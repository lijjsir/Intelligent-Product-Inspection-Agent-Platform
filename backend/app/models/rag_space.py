from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary, TimestampMixin


class RagSpace(Base, TimestampMixin):
    __tablename__ = "rag_spaces"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    folder_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    index_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RagNode(Base, TimestampMixin):
    __tablename__ = "rag_nodes"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    rag_space_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    parent_id: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, default="folder")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_path: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    children_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RagDocument(Base, TimestampMixin):
    __tablename__ = "rag_documents"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    rag_space_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    node_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    uploaded_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    bucket: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="parsed")
    index_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class RagDocumentChunk(Base, TimestampMixin):
    __tablename__ = "rag_document_chunks"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    rag_space_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    document_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    node_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_preview: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qdrant_point_id: Mapped[str] = mapped_column(String(191), nullable=False, default="")


class RagIndexJob(Base, TimestampMixin):
    __tablename__ = "rag_index_jobs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    rag_space_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    document_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
