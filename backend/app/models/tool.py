from sqlalchemy import String, Integer, Boolean, DateTime, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class ToolRegistry(Base):
    """Legacy compatibility table retained for migration and rollback safety only."""

    __tablename__ = "tool_registry"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    display_name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    parameters_schema: Mapped[dict] = mapped_column(JSON)
    returns_schema: Mapped[dict] = mapped_column(JSON)
    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=30000)
    retry_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    access_roles: Mapped[list] = mapped_column(JSON)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=60)
    is_readonly: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")

    category: Mapped[str] = mapped_column(String(64), default="inspection_calc")
    tool_type: Mapped[str] = mapped_column(String(32), default="native")
    status: Mapped[str] = mapped_column(String(32), default="active")
    risk_level: Mapped[str] = mapped_column(String(32), default="low")
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    task_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    tool_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    tool_name: Mapped[str] = mapped_column(String(128))
    call_index: Mapped[int] = mapped_column(Integer, default=0)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    agent_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_type: Mapped[str] = mapped_column(String(32), default="runtime")
    input_redacted: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_redacted: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)

    tool_key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    is_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    active_version_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_checked_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)

    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        UniqueConstraint("org_id", "tool_key", name="uk_org_tool_key"),
    )


class ToolVersion(Base):
    __tablename__ = "tool_versions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    tool_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)

    version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    handler_path: Mapped[str | None] = mapped_column(String(256), nullable=True)

    parameters_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    returns_schema: Mapped[dict] = mapped_column(JSON, nullable=False)

    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    secret_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)

    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=30000)
    retry_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("org_id", "tool_id", "version", name="uk_tool_version"),
    )


class AgentToolBinding(Base):
    __tablename__ = "agent_tool_bindings"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)

    agent_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    tool_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    tool_version_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)

    binding_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    allowed_intents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_call_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("org_id", "agent_id", "tool_id", name="uk_agent_tool"),
    )


class ToolSyncEvent(Base):
    __tablename__ = "tool_sync_events"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    tool_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    old_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=func.now(),
    )


class ToolRuntimeEvent(Base):
    __tablename__ = "tool_runtime_events"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)

    tool_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    execution_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)

    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False), nullable=False,
        server_default=func.now(),
    )
