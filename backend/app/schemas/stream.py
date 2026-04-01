from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StreamSessionCreateRequest(BaseModel):
    resource: str = Field(..., pattern="^(chat|task)$")
    resource_id: str


class StreamSessionResponse(BaseModel):
    stream_token: str
    expires_at: datetime
    resource: str
    resource_id: str
