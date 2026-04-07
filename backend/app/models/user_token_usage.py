from __future__ import annotations

from sqlalchemy import DateTime, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class UserTokenUsageSummary(Base):
    __tablename__ = "user_token_usage_summary"

    user_id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    total_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[float] = mapped_column(Numeric(12, 4), default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    last_ledger_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
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
