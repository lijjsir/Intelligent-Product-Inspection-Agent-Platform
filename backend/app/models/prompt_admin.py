from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary, TimestampMixin


class PromptDefinition(Base, TimestampMixin):
    __tablename__ = "prompt_definitions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)

    prompt_key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stage_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stage_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    usage_location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="code")
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_symbol: Mapped[str | None] = mapped_column(String(160), nullable=True)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)

    code_default_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    active_version_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)

    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="synced")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PromptSyncEvent(Base, TimestampMixin):
    __tablename__ = "prompt_sync_events"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    prompt_definition_id: Mapped[str] = mapped_column(UUIDBinary, index=True)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    old_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
