from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    product_id: str
    spec_id: str
    image_urls: List[str]
    priority: int = Field(default=5, ge=1, le=10)
    metadata: Optional[dict] = None


class TaskResponse(BaseModel):
    id: str
    org_id: str
    product_id: str
    spec_id: str
    status: str
    priority: int


class TaskStatusResponse(BaseModel):
    id: str
    status: str
