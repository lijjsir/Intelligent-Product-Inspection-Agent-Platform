from pydantic import BaseModel, EmailStr


class CurrentUser(BaseModel):
    user_id: str
    org_id: str
    role: str


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
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: str


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserPasswordReset(BaseModel):
    password: str
