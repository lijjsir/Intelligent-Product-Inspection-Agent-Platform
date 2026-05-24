from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    actor_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    report_name: Mapped[str] = mapped_column(String(256), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    template: Mapped[str | None] = mapped_column(String(32), nullable=True, server_default="standard")
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
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
    deleted_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
