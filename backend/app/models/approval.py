from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False, index=True)
    source_module: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    operation_summary: Mapped[str] = mapped_column(String(512), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requester_id: Mapped[str] = mapped_column(UUIDBinary, nullable=False, index=True)
    requester_role: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    review_comment: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
