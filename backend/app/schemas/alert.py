from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator

from app.schemas.common import PageParams


class AlertStatus(str, Enum):
    open = "open"
    acknowledged = "acknowledged"
    suppressed = "suppressed"
    resolved = "resolved"


class AlertAction(str, Enum):
    acknowledge = "acknowledge"
    suppress = "suppress"
    resolve = "resolve"


class AlertListQuery(PageParams):
    status: Optional[str] = None
    severity: Optional[str] = None


class AlertHandleRequest(BaseModel):
    action: AlertAction
    action_note: Optional[str] = None

    @field_validator("action_note")
    @classmethod
    def validate_action_note(cls, v: Optional[str], info) -> Optional[str]:
        action = info.data.get("action")
        if action == AlertAction.suppress:
            if not v or not v.strip():
                raise ValueError("压制操作必须填写备注")
        if v and len(v) > 1024:
            raise ValueError("备注不能超过 1024 个字符")
        return v


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
    suppressed_by: Optional[str] = None
    suppressed_at: Optional[datetime] = None
    action_note: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
