from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class ResultResponse(BaseModel):
    id: str
    task_id: str
    org_id: str
    verdict: str
    overall_score: float


class ReviewSubmit(BaseModel):
    verdict: str
    note: Optional[str] = None
