from sqlalchemy import String, Boolean, DateTime, SmallInteger
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    actor_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    actor_role: Mapped[str] = mapped_column(String(32))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    occurred_at: Mapped[str] = mapped_column(DateTime(timezone=False))


class AuditOutbox(Base):
    __tablename__ = "audit_outbox"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False))
