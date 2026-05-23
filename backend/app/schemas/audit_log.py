from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    org_id: str
    actor_id: str
    actor_role: str
    resource_type: str
    resource_id: str | None = None
    action: str
    payload_hash: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    result_code: int | None = None
    occurred_at: datetime | None = None
