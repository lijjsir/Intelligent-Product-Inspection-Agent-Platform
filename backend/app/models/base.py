from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import DateTime, text
from sqlalchemy.dialects.mysql import BINARY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UUIDBinary(TypeDecorator):
    impl = BINARY(16)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value.bytes
        if isinstance(value, bytes):
            if len(value) == 16:
                return value
            raise ValueError(f"UUIDBinary expects 16 bytes, got {len(value)}")
        try:
            return uuid.UUID(str(value)).bytes
        except (ValueError, AttributeError):
            raise ValueError(f"cannot convert {value!r} to UUID binary") from None

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        return str(uuid.UUID(bytes=value))


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3)"),
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
    )
    deleted_at: Mapped[Any] = mapped_column(DateTime(timezone=False), nullable=True)
