from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.schemas.common import PageParams

class AlertListQuery(PageParams):
    status: Optional[str] = None
    severity: Optional[str] = None

class AlertResponse(BaseModel):
    id: str
    org_id: str
    stability_id: Optional[str] = None
    alert_type: str
    severity: str
    title: str
    detail: Optional[dict] = None
    status: str
    channels: Optional[dict] = None
    dispatched_at: Optional[datetime] = None
    ack_by: Optional[str] = None
    ack_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class AlertHandle(BaseModel):
    status: str
    note: Optional[str] = None
