from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class StabilityResponse(BaseModel):
    id: str
    task_id: str
    result_id: str
    org_id: str
    evidence_score: float
    consistency_score: float
    confidence_score: float
    traceability_score: float
    anomaly_score: float
    risk_score: float
    risk_level: str
    dimension_detail: Optional[dict] = None
    sampling_results: Optional[dict] = None
    root_cause: Optional[str] = None
    handled_by: Optional[str] = None
    handled_at: Optional[str] = None
    handle_action: Optional[str] = None
    handle_note: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}

class HandleRequest(BaseModel):
    action: str
    note: Optional[str] = None
