"""Durable, tenant-scoped supervision records and immutable revision journal."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, DECIMAL, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary


class SupervisionRecord(Base):
    __tablename__ = "supervision_records"
    __table_args__ = (UniqueConstraint("org_id", "kind", "code", name="uq_supervision_code"),)
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(UUIDBinary)
    assigned_to: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class SupervisionRevision(Base):
    __tablename__ = "supervision_revisions"
    __table_args__ = (UniqueConstraint("record_id", "version", name="uq_supervision_revision"),)
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    record_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    version: Mapped[int] = mapped_column(BigInteger)
    actor_id: Mapped[str] = mapped_column(UUIDBinary)
    action: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeviceConnection(Base):
    __tablename__ = "device_connections"
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    device_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MeasurementBatch(Base):
    __tablename__ = "measurement_batches"
    __table_args__ = (
        UniqueConstraint("org_id", "session_id", "source_key", name="uq_measurement_source"),
    )
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    session_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    source_key: Mapped[str] = mapped_column(String(128))
    content_hash: Mapped[str] = mapped_column(String(64))
    raw: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MeasurementRecord(Base):
    __tablename__ = "measurement_records"
    __table_args__ = (
        UniqueConstraint("org_id", "session_id", "event_id", name="uq_measurement_event"),
    )
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    session_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    sample_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    device_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    event_id: Mapped[str] = mapped_column(String(128))
    content_hash: Mapped[str] = mapped_column(String(64))
    command_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    sequence_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    calibration_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupervisionRun(Base):
    __tablename__ = "supervision_runs"
    __table_args__ = (UniqueConstraint("org_id", "request_key", name="uq_supervision_run_key"),)
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    record_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    input_version: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(String(128))
    agent: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[dict] = mapped_column(JSON)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class BusinessReview(Base):
    __tablename__ = "business_reviews"
    __table_args__ = (
        UniqueConstraint("org_id", "record_id", "version", "operation", name="uq_business_review"),
    )
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    record_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    version: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    requester_id: Mapped[str] = mapped_column(UUIDBinary)
    reviewer_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SupervisionDependency(Base):
    __tablename__ = "supervision_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "source_id",
            "source_version",
            "target_id",
            "target_version",
            name="uq_supervision_dependency",
        ),
    )
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    source_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    source_version: Mapped[int] = mapped_column(Integer)
    target_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    target_version: Mapped[int] = mapped_column(Integer)


class InspectionGoal(Base):
    __tablename__ = "inspection_goals"
    __table_args__ = (
        UniqueConstraint("org_id", "session_id", "version", name="uq_inspection_goal_version"),
        UniqueConstraint("org_id", "request_key", name="uq_inspection_goal_key"),
    )
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    session_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    plan_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    risk_hypotheses: Mapped[list] = mapped_column(JSON, default=list)
    required_items: Mapped[list] = mapped_column(JSON, default=list)
    candidate_items: Mapped[list] = mapped_column(JSON, default=list)
    success_criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    stop_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    max_cost: Mapped[float | None] = mapped_column(DECIMAL(14, 2), nullable=True)
    max_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class InspectionEvidenceState(Base):
    __tablename__ = "inspection_evidence_states"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "session_id", "round", name="uq_inspection_evidence_round"
        ),
    )
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    session_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    round: Mapped[int] = mapped_column(Integer)
    device_trust_state: Mapped[dict] = mapped_column(JSON, default=dict)
    product_quality_state: Mapped[dict] = mapped_column(JSON, default=dict)
    supported_hypotheses: Mapped[list] = mapped_column(JSON, default=list)
    rejected_hypotheses: Mapped[list] = mapped_column(JSON, default=list)
    unresolved_conflicts: Mapped[list] = mapped_column(JSON, default=list)
    evidence_sufficiency: Mapped[float] = mapped_column(DECIMAL(5, 4), default=0)
    remaining_uncertainty: Mapped[float] = mapped_column(DECIMAL(5, 4), default=1)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InspectionDecision(Base):
    __tablename__ = "inspection_decisions"
    __table_args__ = (
        UniqueConstraint("org_id", "request_key", name="uq_inspection_decision_key"),
    )
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    session_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    round: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    input_state_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    request_key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    rule_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    proposed_by: Mapped[str] = mapped_column(UUIDBinary)
    approved_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeviceCommand(Base):
    __tablename__ = "device_commands"
    __table_args__ = (UniqueConstraint("org_id", "request_key", name="uq_device_command_key"),)
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    session_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    decision_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    device_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    item_id: Mapped[str] = mapped_column(String(128))
    request_key: Mapped[str] = mapped_column(String(128))
    command: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending_approval", index=True)
    requested_by: Mapped[str] = mapped_column(UUIDBinary)
    approved_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SupervisionEvent(Base):
    __tablename__ = "supervision_events"
    __table_args__ = (
        UniqueConstraint("org_id", "event_key", name="uq_supervision_event_key"),
    )
    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    aggregate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    event_key: Mapped[str] = mapped_column(String(128))
    workflow_run_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
