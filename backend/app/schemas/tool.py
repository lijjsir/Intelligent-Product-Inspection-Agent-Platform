from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class ToolCreate(BaseModel):
    name: str
    display_name: str
    description: str
    parameters_schema: dict
    returns_schema: dict
    access_roles: list[str]
    endpoint: Optional[str] = None


class ToolResponse(BaseModel):
    id: str
    name: str
    display_name: str
    is_active: bool
