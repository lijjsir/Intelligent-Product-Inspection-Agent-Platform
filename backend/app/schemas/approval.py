from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import PageParams


class ApprovalListQuery(PageParams):
    status: str | None = Field(default=None, pattern="^(pending|approved|rejected|cancelled)$")
    source_module: str | None = None
    risk_level: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    requester_id: str | None = None


class ApprovalCreate(BaseModel):
    source_module: str = Field(..., min_length=1, max_length=64)
    source_id: str | None = Field(default=None, max_length=128)
    operation_summary: str = Field(..., min_length=1, max_length=512)
    risk_level: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    payload_json: dict | None = None


class ApprovalReviewRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=1024)


class ApprovalResponse(BaseModel):
    id: str
    org_id: str
    source_module: str
    source_id: str | None = None
    operation_summary: str
    risk_level: str
    payload_json: dict | None = None
    requester_id: str
    requester_role: str
    reviewer_id: str | None = None
    review_comment: str | None = None
    status: str
    created_at: datetime
    reviewed_at: datetime | None = None

    model_config = {"from_attributes": True}
