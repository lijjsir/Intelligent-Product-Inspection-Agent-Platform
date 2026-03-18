from sqlalchemy import String, Integer, DECIMAL, Text, DateTime
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary, TimestampMixin


class InspectionResult(Base, TimestampMixin):
    __tablename__ = "inspection_results"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    task_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    verdict: Mapped[str] = mapped_column(String(32))
    overall_score: Mapped[float] = mapped_column(DECIMAL(5, 4))
    defects: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    citations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reasoning_chain: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
