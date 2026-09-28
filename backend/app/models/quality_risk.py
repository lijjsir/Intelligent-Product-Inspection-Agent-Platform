"""Typed quality-risk domain models for the v4 risk-first workflow."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, UUIDBinary


def new_id() -> str:
    return str(uuid7())


class ProductCategory(Base, TimestampMixin):
    __tablename__ = "product_categories"
    __table_args__ = (UniqueConstraint("org_id", "code", name="uq_product_category_code"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    parent_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class QualityProduct(Base, TimestampMixin):
    __tablename__ = "quality_products"
    __table_args__ = (UniqueConstraint("org_id", "category_id", "name", "model", name="uq_quality_product_identity"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    category_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    manufacturer_enterprise_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductIdentifier(Base, TimestampMixin):
    __tablename__ = "product_identifiers"
    __table_args__ = (UniqueConstraint("org_id", "identifier_type", "identifier_value", "source_id", name="uq_product_identifier_source"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    product_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    identifier_type: Mapped[str] = mapped_column(String(32), index=True)
    identifier_value: Mapped[str] = mapped_column(String(255), index=True)
    source_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)


class EnterpriseProductRelation(Base, TimestampMixin):
    __tablename__ = "enterprise_product_relations"
    __table_args__ = (UniqueConstraint("org_id", "enterprise_id", "product_id", "role", "effective_from", name="uq_enterprise_product_role"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    enterprise_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    product_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)


class QualityDataSource(Base, TimestampMixin):
    __tablename__ = "quality_data_sources"
    __table_args__ = (UniqueConstraint("org_id", "code", name="uq_quality_source_code"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(48), index=True)
    connector_type: Mapped[str] = mapped_column(String(32), index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary)


class QualityIngestionJob(Base, TimestampMixin):
    __tablename__ = "quality_ingestion_jobs"
    __table_args__ = (UniqueConstraint("org_id", "request_key", name="uq_quality_ingestion_key"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    source_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    request_key: Mapped[str] = mapped_column(String(128), index=True)
    import_batch_code: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="preview", index=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(UUIDBinary)


class QualityAttachment(Base, TimestampMixin):
    __tablename__ = "quality_attachments"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    bucket: Mapped[str] = mapped_column(String(128))
    object_key: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[str] = mapped_column(UUIDBinary)


class QualitySourceRecord(Base, TimestampMixin):
    __tablename__ = "quality_source_records"
    __table_args__ = (
        UniqueConstraint("org_id", "source_id", "content_hash", name="uq_quality_source_content"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    source_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    ingestion_job_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    external_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    record_type: Mapped[str] = mapped_column(String(48), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    enterprise_ref: Mapped[dict] = mapped_column(JSON, default=dict)
    product_ref: Mapped[dict] = mapped_column(JSON, default=dict)
    location: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_ids: Mapped[list] = mapped_column(JSON, default=list)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    authorization_scope: Mapped[str] = mapped_column(String(64), default="organization")
    data_nature: Mapped[str] = mapped_column(String(32), default="observed")
    normalization_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    normalization_errors: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(UUIDBinary)


class QualityEvidenceItem(Base, TimestampMixin):
    __tablename__ = "quality_evidence_items"
    __table_args__ = (UniqueConstraint("org_id", "evidence_code", name="uq_quality_evidence_code"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    evidence_code: Mapped[str] = mapped_column(String(128), index=True)
    source_record_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    evidence_type: Mapped[str] = mapped_column(String(48), index=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    nature: Mapped[str] = mapped_column(String(32), default="observed")
    locator: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)


class QualityRiskCase(Base, TimestampMixin):
    __tablename__ = "quality_risk_cases"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="collecting", index=True)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_record_ids: Mapped[list] = mapped_column(JSON, default=list)
    assigned_to: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary)


class QualityRiskAssessment(Base, TimestampMixin):
    __tablename__ = "quality_risk_assessments"
    __table_args__ = (UniqueConstraint("org_id", "risk_case_id", "version", name="uq_quality_risk_assessment_version"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    risk_case_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    risk_type: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    standard_matches: Mapped[list] = mapped_column(JSON, default=list)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    missing_inputs: Mapped[list] = mapped_column(JSON, default=list)
    possible_causes: Mapped[list] = mapped_column(JSON, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    trust_status: Mapped[str] = mapped_column(String(32), default="unverified", index=True)
    probability: Mapped[float | None] = mapped_column(nullable=True)
    model_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    knowledge_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    submitted_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class RiskPolicy(Base, TimestampMixin):
    __tablename__ = "quality_risk_policies"
    __table_args__ = (UniqueConstraint("org_id", "code", "version", name="uq_quality_risk_policy_version"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32))
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary)
    published_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StandardExecutionRule(Base, TimestampMixin):
    __tablename__ = "standard_execution_rules"
    __table_args__ = (
        UniqueConstraint("org_id", "code", "version", name="uq_standard_execution_rule_version"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32))
    standard_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    clause_ref: Mapped[str] = mapped_column(String(255))
    page_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    product_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    indicator: Mapped[str] = mapped_column(String(128))
    method: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    condition: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_action: Mapped[str] = mapped_column(String(64))
    review_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary)
    reviewed_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    published_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PhysicalSample(Base, TimestampMixin):
    __tablename__ = "physical_samples"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    sampling_plan_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    product_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    production_batch_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_sample_code: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    unit_serial_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sampled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sampling_location: Mapped[dict] = mapped_column(JSON, default=dict)
    custody_status: Mapped[str] = mapped_column(String(32), default="planned", index=True)


class MarketMonitoringReport(Base, TimestampMixin):
    __tablename__ = "quality_market_monitoring_reports"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    input_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(UUIDBinary)


class PublicOpinionReport(Base, TimestampMixin):
    __tablename__ = "quality_public_opinion_reports"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    risk_case_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    input_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(UUIDBinary)
