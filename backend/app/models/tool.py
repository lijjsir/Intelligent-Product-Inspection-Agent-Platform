from sqlalchemy import String, Integer, Boolean, DateTime, Text, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class ToolRegistry(Base):
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
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
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
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
    )
