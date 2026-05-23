from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class InfrastructureComponentStatus(BaseModel):
    name: str
    kind: str
    status: str
    latency_ms: int | None = None
    detail: str | None = None
    last_check_at: datetime | None = None


class InfrastructureStatusResponse(BaseModel):
    components: list[InfrastructureComponentStatus]
    overall_status: str
    checked_at: datetime
