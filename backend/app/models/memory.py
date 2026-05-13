from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DECIMAL, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: None)
    memory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    user_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    workspace: Mapped[str] = mapped_column(String(32), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_event_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_pointers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version_parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trust_score: Mapped[float | None] = mapped_column(DECIMAL(5, 4), nullable=True)
    confidence: Mapped[float | None] = mapped_column(DECIMAL(5, 4), nullable=True)
    visibility_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    usage_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="context_only")
    ttl_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="90d")
    privacy_level: Mapped[str] = mapped_column(String(32), nullable=False, default="tenant_private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    rollback_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    created_by_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class MemoryEvent(Base):
    __tablename__ = "memory_events"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: None)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    user_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    workspace: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parent_event_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )


class MemoryDependencyEdge(Base):
    __tablename__ = "memory_dependency_edges"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: None)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    source_memory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_memory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    edge_type: Mapped[str] = mapped_column(String(64), nullable=False)
    strength: Mapped[float | None] = mapped_column(DECIMAL(5, 4), nullable=True)
    scope_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class MemoryPolicy(Base):
    __tablename__ = "memory_policies"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: None)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    workspace: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_key: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class MemoryRollback(Base):
    __tablename__ = "memory_rollbacks"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: None)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    rollback_id: Mapped[str] = mapped_column(String(64), nullable=False)
    root_memory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    workspace: Mapped[str] = mapped_column(String(32), nullable=False)
    rollback_action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_memory_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    propagation_graph_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    before_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    require_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_required")
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )


class MemoryEvaluation(Base):
    __tablename__ = "memory_evaluations"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: None)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    evaluation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rollback_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scenario: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    replay_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
