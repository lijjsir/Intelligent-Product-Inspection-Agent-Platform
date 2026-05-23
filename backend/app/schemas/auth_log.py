from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuthLogResponse(BaseModel):
    id: str
    org_id: str
    user_id: str | None = None
    username: str | None = None
    event_type: str
    ip_address: str | None = None
    user_agent: str | None = None
    success: bool
    detail: str | None = None
    occurred_at: datetime | None = None
