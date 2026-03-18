from fastapi import APIRouter, Depends, Header

from app.api.v1.deps import get_db
from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.core.security import safe_decode_token, create_access_token
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    RegisterRequest,
    AuthSessionResponse,
)
from app.schemas.common import ResponseEnvelope
from app.services.auth_service import AuthService


router = APIRouter()


@router.post("/token", response_model=ResponseEnvelope[AuthSessionResponse])
async def login(
    payload: LoginRequest,
    x_org_id: str = Header(..., alias="X-Org-Id"),
    db=Depends(get_db),
):
    service = AuthService(db)
    user, access, refresh = await service.login(x_org_id, payload.username, payload.password)
    data = AuthSessionResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_exp_minutes * 60,
        user_id=user.id,
        org_id=user.org_id,
        role=user.role,
    )

    return ResponseEnvelope(data=data)


@router.post("/refresh", response_model=ResponseEnvelope[TokenResponse])
async def refresh(payload: RefreshRequest):
    decoded = safe_decode_token(payload.refresh_token)
    if decoded.get("typ") != "refresh":
        raise ForbiddenError("invalid refresh token")

    user_id = decoded.get("sub") or ""
    org_id = decoded.get("org_id") or ""
    role = decoded.get("role") or ""
    if not user_id or not org_id or not role:
        raise ForbiddenError("invalid refresh token")

    access = create_access_token(subject=user_id, extra={"org_id": org_id, "role": role})
    data = TokenResponse(
        access_token=access,
        refresh_token=payload.refresh_token,
        expires_in=settings.jwt_exp_minutes * 60,
    )
    return ResponseEnvelope(data=data)


@router.post("/register", response_model=ResponseEnvelope[AuthSessionResponse])
async def register(payload: RegisterRequest, db=Depends(get_db)):
    service = AuthService(db)
    user, access, refresh = await service.register(
        payload.org_name,
        payload.org_slug,
        payload.username,
        payload.email,
        payload.password,
    )
    data = AuthSessionResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_exp_minutes * 60,
        user_id=user.id,
        org_id=user.org_id,
        role=user.role,
    )
    return ResponseEnvelope(data=data)
