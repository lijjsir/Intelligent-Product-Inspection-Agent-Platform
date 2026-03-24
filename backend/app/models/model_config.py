from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary, TimestampMixin


class ModelConfig(Base, TimestampMixin):
    __tablename__ = "model_configs"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model_key: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    endpoint: Mapped[str] = mapped_column(String(512))
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_type: Mapped[str] = mapped_column(String(32), default="chat")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_price_per_million: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    output_price_per_million: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(16), default="unknown")
    health_message: Mapped[str | None] = mapped_column(String(256), nullable=True)
