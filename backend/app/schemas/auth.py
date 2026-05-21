from pydantic import BaseModel, Field, EmailStr


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="seconds")


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    create_org: bool = True
    org_name: str = ""
    org_slug: str
    username: str
    email: EmailStr
    password: str
    role: str = "admin"


class AuthSessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="seconds")
    user_id: str
    username: str
    org_id: str
    role: str
    roles: list[str] = Field(default_factory=list)
    plan_tier: str = "basic"
    capabilities: list[str] = Field(default_factory=list)
    workspaces: list[str] = Field(default_factory=list)
    default_workspace: str = "app"


# Backwards-compatible alias (older name used by register endpoint).
RegisterResponse = AuthSessionResponse
