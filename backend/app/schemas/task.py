from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import PageParams


class TaskListQuery(PageParams):
    status: Optional[str] = None
    product_id: Optional[str] = None
    ids: Optional[str] = None

    def to_filters(self) -> dict:
        data = {k: v for k, v in self.model_dump(exclude={"page", "size"}).items() if v is not None}
        if data.get("ids"):
            data["ids"] = [item.strip() for item in data["ids"].split(",") if item.strip()]
        return data


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
    image_urls: List[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class TaskListItemResponse(BaseModel):
    id: str
    org_id: str
    product_id: str
    spec_id: str
    status: str
    priority: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskStatusResponse(BaseModel):
    id: str
    status: str

    model_config = {"from_attributes": True}
