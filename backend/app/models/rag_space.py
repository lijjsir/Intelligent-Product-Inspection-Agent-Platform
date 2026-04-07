from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, UUIDBinary, TimestampMixin


class RagSpace(Base, TimestampMixin):
    __tablename__ = "rag_spaces"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    created_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RagSpaceFile(Base, TimestampMixin):
    __tablename__ = "rag_space_files"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    rag_space_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    org_id: Mapped[str] = mapped_column(UUIDBinary, index=True)
    uploaded_by: Mapped[str | None] = mapped_column(UUIDBinary, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
