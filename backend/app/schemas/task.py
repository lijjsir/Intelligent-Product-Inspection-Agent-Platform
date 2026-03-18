from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class TaskListQuery(PageParams):
    status: Optional[str] = None
    product_id: Optional[str] = None

    def to_filters(self) -> dict:
        return {k: v for k, v in self.model_dump(exclude={"page", "size"}).items() if v is not None}


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
    created_at: Optional[str] = None
    
    model_config = {"from_attributes": True}


class TaskStatusResponse(BaseModel):
    id: str
    status: str

    model_config = {"from_attributes": True}
