from sqlalchemy import DateTime, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class TokenUsageLedger(Base):
    __tablename__ = "token_usage_ledger"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    user_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    result_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    model_config_id: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True, index=True)
    model_key: Mapped[str] = mapped_column(String(128), index=True)
    product_line: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(191), nullable=True, unique=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_amount: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
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
