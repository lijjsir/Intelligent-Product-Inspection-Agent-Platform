from sqlalchemy import String, DECIMAL, Text, DateTime
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary, TimestampMixin


class StabilityReport(Base):
    __tablename__ = "stability_reports"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    result_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    task_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    evidence_score: Mapped[float] = mapped_column(DECIMAL(5, 4))
    consistency_score: Mapped[float] = mapped_column(DECIMAL(5, 4))
    confidence_score: Mapped[float] = mapped_column(DECIMAL(5, 4))
    traceability_score: Mapped[float] = mapped_column(DECIMAL(5, 4))
    anomaly_score: Mapped[float] = mapped_column(DECIMAL(5, 4))
    risk_score: Mapped[float] = mapped_column(DECIMAL(5, 2))
    risk_level: Mapped[str] = mapped_column(String(16))
    dimension_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sampling_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    handled_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    handled_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    handle_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    handle_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False))
