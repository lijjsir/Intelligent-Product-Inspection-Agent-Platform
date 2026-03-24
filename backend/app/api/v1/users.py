from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_db, get_current_user
from app.core.claims import normalize_roles
from app.core.permissions import require_role
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.user import (
    UserCreate,
    UserResponse,
    CurrentUser,
    UserRoleUpdate,
    UserStatusUpdate,
    UserPasswordReset,
)
from app.services.user_service import UserService


router = APIRouter()


@router.get("", response_model=ResponseEnvelope[PagedResponse[UserResponse]])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    users, total = await service.list_users(page, size)
    items = [
        UserResponse(
            id=user.id,
            org_id=user.org_id,
            username=user.username,
            email=user.email,
            role=user.role,
            roles=normalize_roles(role=user.role),
            is_active=user.is_active,
        )
        for user in users
    ]
    return ResponseEnvelope(data=PagedResponse(items=items, total=total, page=page, size=size))


@router.get("/me", response_model=ResponseEnvelope[UserResponse])
async def get_me(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    service = UserService(db, current.org_id)
    user = await service.get_user(current.user_id)
    return ResponseEnvelope(
        data=UserResponse(
            id=user.id,
            org_id=user.org_id,
            username=user.username,
            email=user.email,
            role=user.role,
            roles=normalize_roles(role=user.role),
            is_active=user.is_active,
        )
    )


@router.get("/{user_id}", response_model=ResponseEnvelope[UserResponse])
async def get_user(
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.get_user(user_id)
    return ResponseEnvelope(
        data=UserResponse(
            id=user.id,
            org_id=user.org_id,
            username=user.username,
            email=user.email,
            role=user.role,
            roles=normalize_roles(role=user.role),
            is_active=user.is_active,
        )
    )


@router.post("", response_model=ResponseEnvelope[UserResponse])
async def create_user(
    payload: UserCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.create_user(payload.username, payload.email, payload.password, payload.role, current.role)

    return ResponseEnvelope(
        data=UserResponse(
            id=user.id,
            org_id=user.org_id,
            username=user.username,
            email=user.email,
            role=user.role,
            roles=normalize_roles(role=user.role),
            is_active=user.is_active,
        )
    )


@router.patch("/{user_id}/role", response_model=ResponseEnvelope[UserResponse])
async def update_role(
    user_id: str,
    payload: UserRoleUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.update_role(user_id, payload.role, current.role)
    return ResponseEnvelope(
        data=UserResponse(
            id=user.id,
            org_id=user.org_id,
            username=user.username,
            email=user.email,
            role=user.role,
            roles=normalize_roles(role=user.role),
            is_active=user.is_active,
        )
    )


@router.patch("/{user_id}/status", response_model=ResponseEnvelope[UserResponse])
async def update_status(
    user_id: str,
    payload: UserStatusUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.update_status(user_id, payload.is_active)
    return ResponseEnvelope(
        data=UserResponse(
            id=user.id,
            org_id=user.org_id,
            username=user.username,
            email=user.email,
            role=user.role,
            roles=normalize_roles(role=user.role),
            is_active=user.is_active,
        )
    )


@router.patch("/{user_id}/password", response_model=ResponseEnvelope[UserResponse])
async def reset_password(
    user_id: str,
    payload: UserPasswordReset,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.reset_password(user_id, payload.password)
    return ResponseEnvelope(
        data=UserResponse(
            id=user.id,
            org_id=user.org_id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
        )
    )
