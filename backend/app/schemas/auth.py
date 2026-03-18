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
    org_name: str
    org_slug: str
    username: str
    email: EmailStr
    password: str


class AuthSessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="seconds")
    user_id: str
    org_id: str
    role: str


# Backwards-compatible alias (older name used by register endpoint).
RegisterResponse = AuthSessionResponse
