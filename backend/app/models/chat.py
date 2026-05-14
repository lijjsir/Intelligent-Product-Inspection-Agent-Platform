from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary, TimestampMixin


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    user_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    session_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    user_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ChatMessageScore(Base, TimestampMixin):
    __tablename__ = "chat_message_scores"
    __table_args__ = (
        UniqueConstraint("org_id", "assistant_message_id", "score_version", name="uq_chat_message_scores_version"),
        Index("idx_chat_message_scores_org_created", "org_id", "created_at"),
        Index("idx_chat_message_scores_trace", "org_id", "trace_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    session_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    user_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    assistant_message_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    score_version: Mapped[str] = mapped_column(String(32), nullable=False, default="trust_v1")
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    observation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rule_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    combined_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trust_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hallucination_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    overconfidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_citation: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scored")
    langfuse_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
