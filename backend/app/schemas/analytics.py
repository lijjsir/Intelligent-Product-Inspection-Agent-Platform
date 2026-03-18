from __future__ import annotations

from pydantic import BaseModel


class OverviewStats(BaseModel):
    pass_rate: float
    hallucination_rate: float
    risk_yellow_rate: float
