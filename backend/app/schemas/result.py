from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.schemas.common import PageParams


class ResultResponse(BaseModel):
    id: str
    task_id: str
    org_id: str
    verdict: str
    overall_score: float
    defects: Optional[list[dict]] = None
    citations: Optional[dict] = None
    reasoning_chain: Optional[dict] = None
    llm_model: str
    prompt_version: str
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReviewSubmit(BaseModel):
    verdict: str
    note: Optional[str] = None


class ResultListQuery(PageParams):
    verdict: Optional[str] = None
    product_id: Optional[str] = None
    model_key: Optional[str] = None
    task_id: Optional[str] = None


class ResultListItemResponse(BaseModel):
    id: str
    task_id: str
    org_id: str
    product_id: str
    verdict: str
    overall_score: float
    llm_model: str
    prompt_version: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
