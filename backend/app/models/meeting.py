from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
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
