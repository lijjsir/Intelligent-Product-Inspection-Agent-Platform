from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CurrentUser(BaseModel):
    user_id: str
    org_id: str
    role: str
    roles: list[str] = []
    plan_tier: str = "basic"
    capabilities: list[str] = []
    workspaces: list[str] = []
    default_workspace: str = "app"
    stream_resource: str | None = None
    stream_resource_id: str | None = None


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "user"


class UserResponse(BaseModel):
    id: str
    org_id: str
    username: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserRoleUpdate(BaseModel):
    role: str


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserPasswordReset(BaseModel):
    password: str


class UserListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)
    keyword: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserProfileUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    current_password: str | None = None
    new_password: str | None = None
