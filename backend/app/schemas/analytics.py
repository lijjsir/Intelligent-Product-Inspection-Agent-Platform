from __future__ import annotations

from pydantic import BaseModel


class OverviewStats(BaseModel):
    total_tasks: int
    total_alerts: int
    pass_rate: float
    hallucination_rate: float
    risk_yellow_rate: float
