from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
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
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


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
