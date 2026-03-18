from sqlalchemy import String, SmallInteger, DateTime
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary, TimestampMixin


class InspectionTask(Base, TimestampMixin):
    __tablename__ = "inspection_tasks"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str] = mapped_column(UUIDBinary, index=True)
    product_id: Mapped[str] = mapped_column(String(64))
    spec_id: Mapped[str] = mapped_column(String(64))
    strategy_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    image_urls: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    priority: Mapped[int] = mapped_column(SmallInteger, default=5)
    meta_data: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    started_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
