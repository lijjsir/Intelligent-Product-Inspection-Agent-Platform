from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., min_length=1, max_length=64)
    plan: str = Field(default="standard", min_length=1, max_length=32)
    settings: dict | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    plan: str | None = Field(default=None, min_length=1, max_length=32)
    settings: dict | None = None
    is_active: bool | None = None


class OrganizationSummary(BaseModel):
    id: str
    name: str


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    settings: dict | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    user_count: int = 0


class OrganizationUserAssignRequest(BaseModel):
    user_ids: list[str] = Field(..., min_length=1)
    action: str = Field(..., pattern="^(assign|remove)$")


class OrganizationUserItem(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool


class OrganizationUsersResponse(BaseModel):
    organization: OrganizationSummary
    users: list[OrganizationUserItem]
    total: int
