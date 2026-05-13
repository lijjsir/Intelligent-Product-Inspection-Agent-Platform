from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.mysql import JSON
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
    product_family: Mapped[str | None] = mapped_column(String(128), nullable=True)
    applicable_skus: Mapped[list | None] = mapped_column(JSON, nullable=True)
    required_views: Mapped[list | None] = mapped_column(JSON, nullable=True)
    effective_from: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    effective_to: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    required_image_count: Mapped[int] = mapped_column(Integer, default=1)
    ai_gate_confidence_threshold: Mapped[float] = mapped_column(Numeric(5, 4), default=0.72)
    ai_gate_evidence_threshold: Mapped[float] = mapped_column(Numeric(5, 4), default=0.5)
    ai_gate_traceability_threshold: Mapped[float] = mapped_column(Numeric(5, 4), default=0.5)
    aggregation_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_gate_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    manual_review_policies: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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


class DefectTaxonomy(Base, TimestampMixin):
    __tablename__ = "defect_taxonomy"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    defect_code: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    default_severity: Mapped[str] = mapped_column(String(16), default="major")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProductZoneMap(Base, TimestampMixin):
    __tablename__ = "product_zone_maps"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    spec_row_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    zone_code: Mapped[str] = mapped_column(String(32), index=True)
    zone_name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)


class SpecAggregationRule(Base, TimestampMixin):
    __tablename__ = "spec_aggregation_rules"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    spec_row_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    rule_code: Mapped[str] = mapped_column(String(64), index=True)
    rule_name: Mapped[str] = mapped_column(String(128))
    rule_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SpecChangeLog(Base, TimestampMixin):
    __tablename__ = "spec_change_logs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    spec_row_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    changed_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    version: Mapped[str] = mapped_column(String(32))
    change_summary: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InspectionResultEvidence(Base, TimestampMixin):
    __tablename__ = "inspection_result_evidence"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    result_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    task_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), index=True)
    uri: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
