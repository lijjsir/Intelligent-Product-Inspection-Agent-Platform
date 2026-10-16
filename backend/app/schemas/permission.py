from typing import Literal

from pydantic import BaseModel, Field


class RolePermissionUpdate(BaseModel):
    resources: list[str] = Field(max_length=200)
    version: int = Field(ge=0)


class UserPermissionUpdate(BaseModel):
    role: str
    expected_role: str
    overrides: dict[str, Literal["grant", "deny"]] = Field(default_factory=dict, max_length=200)
    version: int = Field(ge=0)
