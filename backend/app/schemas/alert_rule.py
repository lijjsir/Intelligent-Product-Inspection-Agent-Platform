from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.common import PageParams


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = None
    alert_type: str = Field(min_length=1, max_length=64)
    severity: str = Field(default="warning", pattern=r"^(critical|error|warning|info)$")
    enabled: bool = True
    condition_config: Optional[dict] = None
    notification_channels: Optional[dict] = None
    cooldown_seconds: int = Field(default=300, ge=0, le=86400)


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    alert_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    severity: Optional[str] = Field(default=None, pattern=r"^(critical|error|warning|info)$")
    enabled: Optional[bool] = None
    condition_config: Optional[dict] = None
    notification_channels: Optional[dict] = None
    cooldown_seconds: Optional[int] = Field(default=None, ge=0, le=86400)


class AlertRuleListQuery(PageParams):
    status: Optional[str] = None
    severity: Optional[str] = None
    enabled: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    id: str
    org_id: str
    name: str
    description: Optional[str] = None
    alert_type: str
    severity: str
    enabled: bool
    condition_config: Optional[dict] = None
    notification_channels: Optional[dict] = None
    cooldown_seconds: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
