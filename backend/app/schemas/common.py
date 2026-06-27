from __future__ import annotations

from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)


class PagedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int


class ResponseEnvelope(BaseModel, Generic[T]):
    success: bool = True
    code: str = "ok"
    message: str = "success"
    data: Optional[T] = None
    trace_id: Optional[str] = None
    warnings: List[dict | str] = Field(default_factory=list)
