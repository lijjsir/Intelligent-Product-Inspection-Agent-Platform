from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import DateTime
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
            return value
        return uuid.UUID(str(value)).bytes

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        return str(uuid.UUID(bytes=value))


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=False))
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=False))
    deleted_at: Mapped[Any] = mapped_column(DateTime(timezone=False), nullable=True)
