from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_db, get_current_user
from app.core.claims import normalize_roles
from app.core.permissions import require_role
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.user import (
    CurrentUser,
    UserCreate,
    UserListQuery,
    UserPasswordReset,
    UserProfileUpdate,
    UserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.services.user_service import UserService


router = APIRouter()


def _to_response(user) -> UserResponse:
    return UserResponse(
        id=user.id,
        org_id=user.org_id,
        username=user.username,
        email=user.email,
        role=user.role,
        roles=normalize_roles(role=user.role),
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("", response_model=ResponseEnvelope[PagedResponse[UserResponse]])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    keyword: str | None = Query(default=None, min_length=1, max_length=128),
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    query = UserListQuery(page=page, size=size, keyword=keyword, role=role, is_active=is_active)
    users, total = await service.list_users(
        query.page,
        query.size,
        query.keyword,
        query.role,
        query.is_active,
    )
    items = [_to_response(user) for user in users]
    return ResponseEnvelope(data=PagedResponse(items=items, total=total, page=page, size=size))


@router.get("/meta/assignable-roles", response_model=ResponseEnvelope[list[str]])
async def list_assignable_roles(
    current: CurrentUser = Depends(get_current_user),
):
    require_role("user", current.role)
    return ResponseEnvelope(data=UserService.get_assignable_roles(current.role))


@router.get("/me", response_model=ResponseEnvelope[UserResponse])
async def get_me(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    service = UserService(db, current.org_id)
    user = await service.get_user(current.user_id)
    return ResponseEnvelope(data=_to_response(user))


@router.patch("/me", response_model=ResponseEnvelope[UserResponse])
async def update_me(
    payload: UserProfileUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    service = UserService(db, current.org_id)
    user = await service.update_profile(
        current.user_id,
        username=payload.username,
        email=payload.email,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    await db.refresh(user)
    return ResponseEnvelope(data=_to_response(user))


@router.get("/{user_id}", response_model=ResponseEnvelope[UserResponse])
async def get_user(
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.get_user(user_id)
    return ResponseEnvelope(data=_to_response(user))


@router.post("", response_model=ResponseEnvelope[UserResponse])
async def create_user(
    payload: UserCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.create_user(payload.username, payload.email, payload.password, payload.role, current.role)
    await db.refresh(user)
    return ResponseEnvelope(data=_to_response(user))


@router.patch("/{user_id}/role", response_model=ResponseEnvelope[UserResponse])
async def update_role(
    user_id: str,
    payload: UserRoleUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.update_role(user_id, payload.role, current.role, current.user_id)
    await db.refresh(user)
    return ResponseEnvelope(data=_to_response(user))


@router.patch("/{user_id}/status", response_model=ResponseEnvelope[UserResponse])
async def update_status(
    user_id: str,
    payload: UserStatusUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.update_status(user_id, payload.is_active, current.user_id)
    await db.refresh(user)
    return ResponseEnvelope(data=_to_response(user))


@router.patch("/{user_id}/password", response_model=ResponseEnvelope[UserResponse])
async def reset_password(
    user_id: str,
    payload: UserPasswordReset,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("user", current.role)
    service = UserService(db, current.org_id)
    user = await service.reset_password(user_id, payload.password, current.user_id)
    await db.refresh(user)
    return ResponseEnvelope(data=_to_response(user))
