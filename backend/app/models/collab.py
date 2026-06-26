from __future__ import annotations

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, UUIDBinary


class CollabThread(Base, TimestampMixin):
    __tablename__ = "collab_threads"
    __table_args__ = (
        Index("idx_collab_threads_org_source", "org_id", "source_type", "source_id"),
        Index("idx_collab_threads_org_target", "org_id", "target_type", "target_id"),
        Index("idx_collab_threads_org_last_message", "org_id", "last_message_at"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    thread_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by: Mapped[str] = mapped_column(UUIDBinary, index=True)
    last_message_at: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CollabThreadParticipant(Base, TimestampMixin):
    __tablename__ = "collab_thread_participants"
    __table_args__ = (
        UniqueConstraint(
            "thread_id",
            "participant_type",
            "participant_id",
            name="uq_collab_thread_participant",
        ),
        Index(
            "idx_collab_participants_lookup",
            "org_id",
            "participant_type",
            "participant_id",
        ),
        Index("idx_collab_participants_thread", "org_id", "thread_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    thread_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    participant_type: Mapped[str] = mapped_column(String(32), nullable=False)
    participant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="participant")
    last_read_message_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    mute_until: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)


class CollabMessage(Base, TimestampMixin):
    __tablename__ = "collab_messages"
    __table_args__ = (
        Index("idx_collab_messages_thread_created", "thread_id", "created_at"),
        Index("idx_collab_messages_org_thread", "org_id", "thread_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    thread_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    sender_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sender_id: Mapped[str] = mapped_column(String(128), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reply_to_message_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CollabMessageReceipt(Base, TimestampMixin):
    __tablename__ = "collab_message_receipts"
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "recipient_type",
            "recipient_id",
            name="uq_collab_message_receipt",
        ),
        Index(
            "idx_collab_receipts_recipient",
            "org_id",
            "recipient_type",
            "recipient_id",
            "read_at",
        ),
        Index("idx_collab_receipts_message", "message_id", "recipient_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    message_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    thread_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    recipient_type: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_id: Mapped[str] = mapped_column(String(128), nullable=False)
    delivered_at: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)
    read_at: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)
    acted_at: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)
    action_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")


class FileAsset(Base, TimestampMixin):
    __tablename__ = "file_assets"
    __table_args__ = (
        Index("idx_file_assets_org_uploaded", "org_id", "uploaded_by"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    uploaded_by: Mapped[str] = mapped_column(UUIDBinary, index=True)


class MessageAttachment(Base, TimestampMixin):
    __tablename__ = "message_attachments"
    __table_args__ = (
        UniqueConstraint("message_id", "file_id", name="uq_message_attachment_file"),
        Index("idx_message_attachments_message", "message_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    message_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    file_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
