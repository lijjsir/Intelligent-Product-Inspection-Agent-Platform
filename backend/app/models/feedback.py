from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDBinary


class ResultFeedback(Base):
    __tablename__ = "result_feedbacks"
    __table_args__ = (UniqueConstraint("actor_id", "result_id", name="uk_actor_result"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    result_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    actor_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    feedback_type: Mapped[str] = mapped_column(String(16))
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class MessageFeedback(Base):
    __tablename__ = "message_feedbacks"
    __table_args__ = (
        UniqueConstraint("actor_id", "target_type", "target_id", name="uk_actor_message_feedback"),
        Index("idx_message_feedbacks_org_target", "org_id", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    target_type: Mapped[str] = mapped_column(String(24), index=True)
    target_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    actor_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    feedback_type: Mapped[str] = mapped_column(String(16))
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
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
