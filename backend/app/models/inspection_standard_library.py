from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, UUIDBinary


class InspectionStandardLibrary(Base, TimestampMixin):
    __tablename__ = "inspection_standard_libraries"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    product_family: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rag_space_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    product_category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    qdrant_collection: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pdf_root_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_glob: Mapped[str] = mapped_column(String(64), default="*.pdf", nullable=False)
    chunk_strategy: Mapped[str] = mapped_column(String(32), default="heading_then_size", nullable=False)
    standard_status: Mapped[str] = mapped_column(String(32), default="现行", nullable=False)
    auto_reindex: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pdf_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    import_status: Mapped[str] = mapped_column(String(32), default="not_scanned", nullable=False)
    last_scanned_at: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_indexed_at: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class StandardDocument(Base, TimestampMixin):
    __tablename__ = "standard_documents"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    library_id: Mapped[str] = mapped_column(
        UUIDBinary,
        ForeignKey("inspection_standard_libraries.id"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    product_category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    standard_no: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    standard_name: Mapped[str] = mapped_column(String(255), nullable=False)
    standard_level: Mapped[str] = mapped_column(String(32), nullable=False)
    standard_status: Mapped[str] = mapped_column(String(32), default="现行", nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qdrant_collection: Mapped[str | None] = mapped_column(String(128), nullable=True)
    import_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    last_indexed_at: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class StandardDocumentChunk(Base, TimestampMixin):
    __tablename__ = "standard_document_chunks"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    document_id: Mapped[str] = mapped_column(UUIDBinary, ForeignKey("standard_documents.id"), nullable=False, index=True)
    library_id: Mapped[str] = mapped_column(UUIDBinary, ForeignKey("inspection_standard_libraries.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    qdrant_point_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
