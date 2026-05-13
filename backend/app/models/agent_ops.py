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


class PromptDSPyConfig(Base, TimestampMixin):
    __tablename__ = "prompt_dspy_configs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    prompt_version_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    module_name: Mapped[str] = mapped_column(String(128), nullable=False)
    compiler_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_names: Mapped[list | None] = mapped_column(JSON, nullable=True)
    config_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)


class DSPyOptimizationConfig(Base, TimestampMixin):
    __tablename__ = "dspy_optimization_configs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    target_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    subgraph_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    node_label: Mapped[str] = mapped_column(String(128), nullable=False)
    module_name: Mapped[str] = mapped_column(String(128), nullable=False)
    optimization_goal: Mapped[str] = mapped_column(Text, nullable=False)
    optimizer_strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="bootstrap-fewshot")
    compiler_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metric_names: Mapped[list | None] = mapped_column(JSON, nullable=True)
    config_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active_target: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_compile: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_artifact_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_prompt_version_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    previous_artifact_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_prompt_version_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    latest_failed_artifact_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latest_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_metrics_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_compiled_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_evaluated_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)


class DSPyOptimizationRun(Base, TimestampMixin):
    __tablename__ = "dspy_optimization_runs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    target_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, default="compile")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    compiler_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)


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


class RagQueryLog(Base, TimestampMixin):
    __tablename__ = "rag_query_logs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    task_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    rag_space_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    citation_coverage: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_graph: Mapped[str] = mapped_column(String(64), nullable=False, default="quality_judgement")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
