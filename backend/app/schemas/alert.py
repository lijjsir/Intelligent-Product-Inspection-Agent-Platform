from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: str
    org_id: str
    severity: str
    status: str
    title: str


class AlertHandle(BaseModel):
    status: str
    note: Optional[str] = None
