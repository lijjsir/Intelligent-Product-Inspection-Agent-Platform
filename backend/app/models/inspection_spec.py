from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDBinary


class InspectionSpec(Base, TimestampMixin):
    __tablename__ = "inspection_specs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    spec_code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32), default="v1")
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    required_image_count: Mapped[int] = mapped_column(Integer, default=1)
    ai_gate_confidence_threshold: Mapped[float] = mapped_column(Numeric(5, 4), default=0.72)
    ai_gate_evidence_threshold: Mapped[float] = mapped_column(Numeric(5, 4), default=0.5)
    ai_gate_traceability_threshold: Mapped[float] = mapped_column(Numeric(5, 4), default=0.5)
    auto_pass_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InspectionSpecItem(Base, TimestampMixin):
    __tablename__ = "inspection_spec_items"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    spec_row_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    defect_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="major")
    disposition: Mapped[str] = mapped_column(String(32), default="fail")
    confidence_threshold: Mapped[float] = mapped_column(Numeric(5, 4), default=0.55)
    zone_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
