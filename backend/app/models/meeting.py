from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, UUIDBinary


class MeetingRoom(Base, TimestampMixin):
    __tablename__ = "meeting_rooms"
    __table_args__ = (
        UniqueConstraint("org_id", "access_code", name="uq_meeting_rooms_org_code"),
        Index("idx_meeting_rooms_org_status", "org_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    access_code: Mapped[str] = mapped_column(String(16), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class MeetingRoomMember(Base, TimestampMixin):
    __tablename__ = "meeting_room_members"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_meeting_room_members_user"),
        Index("idx_meeting_room_members_org_user", "org_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    room_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    user_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="member")


class MeetingRoomAgent(Base, TimestampMixin):
    __tablename__ = "meeting_room_agents"
    __table_args__ = (
        UniqueConstraint("room_id", "agent_id", name="uq_meeting_room_agents_room_agent"),
        Index("idx_meeting_room_agents_room", "room_id"),
        Index("idx_meeting_room_agents_org_room", "org_id", "room_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    room_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    added_by: Mapped[str] = mapped_column(UUIDBinary, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="participant")


class MeetingAgentDefinition(Base, TimestampMixin):
    __tablename__ = "meeting_agent_definitions"
    __table_args__ = (
        Index("idx_mad_org_active", "org_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="deepseek-chat")
    adapter_type: Mapped[str] = mapped_column(String(32), nullable=False, default="llm")
    participation_strategy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, index=True, nullable=True)


class MeetingMessage(Base, TimestampMixin):
    __tablename__ = "meeting_messages"
    __table_args__ = (
        UniqueConstraint("room_id", "seq_no", name="uq_meeting_messages_room_seq"),
        Index("idx_meeting_messages_org_room", "org_id", "room_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    room_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    user_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    mentions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quote_message_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class MemoryScopeBinding(Base, TimestampMixin):
    __tablename__ = "memory_scope_bindings"
    __table_args__ = (
        Index("idx_memory_scope_bindings_memory", "org_id", "memory_id"),
        Index("idx_memory_scope_bindings_scope", "org_id", "scope_type", "scope_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    memory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    permission: Mapped[str] = mapped_column(String(32), nullable=False, default="read")
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)


class MemoryTransferLog(Base, TimestampMixin):
    __tablename__ = "memory_transfer_logs"
    __table_args__ = (
        Index("idx_memory_transfer_logs_memory", "org_id", "memory_id"),
        Index("idx_memory_transfer_logs_target", "org_id", "to_scope_type", "to_scope_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    memory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    to_scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    to_scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    transfer_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    operator_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)


class MeetingActionItem(Base, TimestampMixin):
    __tablename__ = "meeting_action_items"
    __table_args__ = (
        Index("idx_meeting_action_items_room_status", "org_id", "room_id", "status"),
        Index("idx_meeting_action_items_owner", "org_id", "owner_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    room_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    source_message_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary, index=True)
