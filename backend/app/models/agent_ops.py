from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary, TimestampMixin


class AgentDefinition(Base, TimestampMixin):
    """
    Agent definitions for workflow orchestration.
    Indexes:
      - PRIMARY KEY (id)
      - idx_org_name (org_id, name)
      - idx_org_active (org_id, is_active)
    """
    __tablename__ = "agent_definitions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    workflow_binding: Mapped[str | None] = mapped_column(String(100), nullable=True)
    intent_config_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    subgraph_key: Mapped[str] = mapped_column(String(64), nullable=False, default="quality_judgement")
    entry_graph: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supports_start_stop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    graph_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 新增：产品化字段
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", comment="active/partial/planned/legacy/deprecated")
    group_key: Mapped[str] = mapped_column(String(32), nullable=False, default="core", comment="core/memory/planned/legacy")
    route_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否参与路由")
    supports_route_toggle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否允许暂停恢复路由")
    customer_visible_description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="给客户看的能力说明")


class PromptVersion(Base, TimestampMixin):
    """
    Prompt version management for agent configuration.
    Indexes:
      - PRIMARY KEY (id)
      - idx_org_name_version (org_id, name, version)
      - idx_org_status (org_id, status)
    """
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    prompt_definition_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntentRoute(Base, TimestampMixin):
    """
    Intent routing configuration for agent dispatch.
    Indexes:
      - PRIMARY KEY (id)
      - idx_org_intent (org_id, intent_name)
      - idx_org_active_priority (org_id, is_active, priority)
    """
    __tablename__ = "intent_routes"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    intent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AgentRuntimeInstance(Base, TimestampMixin):
    __tablename__ = "agent_runtime_instances"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    agent_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    runtime_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    subgraph_key: Mapped[str] = mapped_column(String(64), nullable=False, default="quality_judgement")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="stopped")
    supports_start_stop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_started_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_stopped_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    # 新增：增强运行态字段
    runtime_status: Mapped[str] = mapped_column(String(32), nullable=False, default="stopped", comment="running/stopped/degraded/maintenance/readonly")
    last_health_check_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    maintenance_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)


class RagQueryLog(Base, TimestampMixin):
    __tablename__ = "rag_query_logs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    task_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    rag_space_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    citation_coverage: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_graph: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sub_route: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    top_score: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AgentRouteLog(Base, TimestampMixin):
    """Agent routing audit log — tracks every route decision made by AgentManager.
    Indexes:
      - PRIMARY KEY (id)
      - idx_route_logs_session (org_id, session_id, created_at)
      - idx_route_logs_agent (org_id, selected_agent, created_at)
    """
    __tablename__ = "agent_route_logs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    user_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    session_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    intent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    route_source: Mapped[str] = mapped_column(String(32), nullable=False, default="rule")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_route: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    fallback_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signals_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 新增：运行态阻止
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否被运行态阻止")
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="阻止原因")


class AgentRuntimeEvent(Base, TimestampMixin):
    """Agent 运行态操作事件日志 — pause_route/resume_route/start/stop/maintenance"""
    __tablename__ = "agent_runtime_events"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    agent_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    runtime_key: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="pause_route/resume_route/start/stop/maintenance")
    before_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    after_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
