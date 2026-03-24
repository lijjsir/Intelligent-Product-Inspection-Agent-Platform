from pydantic import BaseModel, EmailStr, Field


class CurrentUser(BaseModel):
    user_id: str
    org_id: str
    role: str
    roles: list[str] = Field(default_factory=list)
    plan_tier: str = "basic"
    capabilities: list[str] = Field(default_factory=list)
    workspaces: list[str] = Field(default_factory=list)
    default_workspace: str = "app"


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "inspector"


class UserResponse(BaseModel):
    id: str
    org_id: str
    username: str
    email: EmailStr
    role: str
    roles: list[str] = Field(default_factory=list)
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: str


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserPasswordReset(BaseModel):
    password: str
