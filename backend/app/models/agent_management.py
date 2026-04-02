from __future__ import annotations

from datetime import datetime
from sqlalchemy import Integer, Boolean, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary, TimestampMixin


class AgentExecutionMetrics(Base, TimestampMixin):
    """
    Agent execution performance metrics.
    Indexes:
      - PRIMARY KEY (id)
      - idx_org_agent_id (org_id, agent_id)
    """
    __tablename__ = "agent_execution_metrics"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    agent_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    execution_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class AgentConfigVersion(Base, TimestampMixin):
    """
    Agent configuration version history.
    Indexes:
      - PRIMARY KEY (id)
      - idx_org_agent_version (org_id, agent_id, version)
    """
    __tablename__ = "agent_config_versions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    agent_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
