from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class StabilityResponse(BaseModel):
    id: str
    task_id: str
    risk_score: float
    risk_level: str


class HandleRequest(BaseModel):
    action: str
    note: Optional[str] = None
