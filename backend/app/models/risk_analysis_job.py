"""Durable risk-analysis requests; never professional review decisions."""
from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDBinary
from app.core.ids import uuid7
from app.core.datetime import utcnow


class RiskAnalysisJob(Base):
    __tablename__ = 'risk_analysis_jobs'
    __table_args__ = (UniqueConstraint('org_id','request_key'),Index('ix_risk_analysis_dispatch','status','created_at'),)
    id: Mapped[str] = mapped_column(UUIDBinary,primary_key=True,default=lambda:str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary,index=True)
    case_id: Mapped[str] = mapped_column(UUIDBinary,ForeignKey('quality_risk_cases.id'),index=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary)
    request_key: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON)
    basis_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32),default='queued')
    claim_token: Mapped[str | None] = mapped_column(String(36),nullable=True)
    assessment_id: Mapped[str | None] = mapped_column(UUIDBinary,nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(48),nullable=True)
    message: Mapped[str] = mapped_column(String(500),default='请求已保存，等待后台分析')
    created_at: Mapped[object] = mapped_column(DateTime,default=utcnow)
    started_at: Mapped[object | None] = mapped_column(DateTime,nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime,nullable=True)
    lease_until: Mapped[object | None] = mapped_column(DateTime,nullable=True)
