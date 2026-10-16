"""Standard admission is separate from parsing and vector readiness."""
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary
from app.core.datetime import utcnow


class StandardDocumentRevision(Base):
    __tablename__ = "standard_document_revisions"
    __table_args__ = (UniqueConstraint("document_id", "revision_no"),)
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    document_id: Mapped[str] = mapped_column(UUIDBinary, ForeignKey("standard_documents.id"), index=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="pending")
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    publication_status: Mapped[str] = mapped_column(String(32), default="unpublished")
    extraction_status: Mapped[str] = mapped_column(String(32), default="pending")
    pages_json: Mapped[list] = mapped_column(JSON, default=list)
    candidates_json: Mapped[list] = mapped_column(JSON, default=list)
    issues_json: Mapped[list] = mapped_column(JSON, default=list)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    index_generation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    published_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    review_assignment: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)


class StandardAdmissionReview(Base):
    __tablename__ = "standard_admission_reviews"
    __table_args__ = (UniqueConstraint("org_id", "request_key"),)
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    revision_id: Mapped[str] = mapped_column(UUIDBinary, ForeignKey("standard_document_revisions.id"), index=True)
    action: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(UUIDBinary)
    request_key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class StandardSyncOutbox(Base):
    __tablename__ = "standard_sync_outbox"
    __table_args__ = (UniqueConstraint("revision_id", "action", "generation"),)
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    revision_id: Mapped[str] = mapped_column(UUIDBinary, ForeignKey("standard_document_revisions.id"))
    action: Mapped[str] = mapped_column(String(32))
    generation: Mapped[str] = mapped_column(String(64), default="initial")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
