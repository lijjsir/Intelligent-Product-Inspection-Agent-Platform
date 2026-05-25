from sqlalchemy import String, Text, DateTime, text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    stability_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    alert_type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(256))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    channels: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(512), nullable=True, unique=True)
    dispatched_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    ack_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    ack_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    resolved_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    suppressed_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    suppressed_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    action_note: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
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
