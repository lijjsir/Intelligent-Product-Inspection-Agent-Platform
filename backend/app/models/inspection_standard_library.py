from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDBinary


class InspectionStandardLibrary(Base, TimestampMixin):
    __tablename__ = "inspection_standard_libraries"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    product_family: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rag_space_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
