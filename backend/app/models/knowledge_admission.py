from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDBinary
from app.core.datetime import utcnow
from app.core.ids import uuid7


class RagSpaceGrant(Base):
    __tablename__ = "rag_space_grants"
    __table_args__ = (UniqueConstraint("org_id","space_id","user_id"),)
    id: Mapped[str] = mapped_column(UUIDBinary,primary_key=True,default=lambda:str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary,index=True)
    space_id: Mapped[str] = mapped_column(UUIDBinary,ForeignKey("rag_spaces.id"),index=True)
    user_id: Mapped[str] = mapped_column(UUIDBinary,index=True)
    granted_by: Mapped[str] = mapped_column(UUIDBinary)
    status: Mapped[str] = mapped_column(String(32),default="active")
    row_version: Mapped[int] = mapped_column(Integer,default=1)
    reason: Mapped[str] = mapped_column(Text)
    allow_knowledge_submission: Mapped[bool] = mapped_column(Boolean,default=False)
    created_at: Mapped[object] = mapped_column(DateTime,default=utcnow)
    revoked_at: Mapped[object|None] = mapped_column(DateTime,nullable=True)


class KnowledgeAdmission(Base):
    __tablename__ = "knowledge_admissions"
    __table_args__ = (UniqueConstraint("org_id","created_by","request_key"),)
    id: Mapped[str] = mapped_column(UUIDBinary,primary_key=True,default=lambda:str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary,index=True)
    memory_id: Mapped[str] = mapped_column(String(64),unique=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary,index=True)
    request_key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    source_refs: Mapped[list] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(32),default="pending")
    sharing_status: Mapped[str] = mapped_column(String(32),default="pending")
    publication_status: Mapped[str] = mapped_column(String(32),default="unpublished")
    row_version: Mapped[int] = mapped_column(Integer,default=1)
    reviewed_by: Mapped[str|None] = mapped_column(UUIDBinary,nullable=True)
    share_approved_by: Mapped[str|None] = mapped_column(UUIDBinary,nullable=True)
    published_by: Mapped[str|None] = mapped_column(UUIDBinary,nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime,default=utcnow)
    reviewed_at: Mapped[object|None] = mapped_column(DateTime,nullable=True)
    published_at: Mapped[object|None] = mapped_column(DateTime,nullable=True)


class KnowledgeAdmissionAction(Base):
    __tablename__ = "knowledge_admission_actions"
    __table_args__ = (UniqueConstraint("org_id","request_key"),)
    id: Mapped[str] = mapped_column(UUIDBinary,primary_key=True,default=lambda:str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary,index=True)
    admission_id: Mapped[str] = mapped_column(UUIDBinary,ForeignKey("knowledge_admissions.id"),index=True)
    actor_id: Mapped[str] = mapped_column(UUIDBinary)
    action: Mapped[str] = mapped_column(String(32))
    request_key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON,default=dict)
    created_at: Mapped[object] = mapped_column(DateTime,default=utcnow)
