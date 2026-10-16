from uuid import UUID

from fastapi import Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.claims import (
    derive_capabilities,
    derive_default_workspace,
    derive_plan_tier,
    derive_workspaces,
    normalize_roles,
)
from app.core.security import safe_decode_token
from app.core.exceptions import ForbiddenError
from app.core.permissions import PermissionRole
from app.schemas.user import CurrentUser
from infra.database.session import get_session


async def get_db() -> AsyncSession:
    async with get_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _require_uuid_claim(payload: dict, key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ForbiddenError("invalid token claims")
    try:
        return str(UUID(value))
    except (TypeError, ValueError):
        raise ForbiddenError("invalid token claims") from None


async def get_permission_identity(
    authorization: str = Header(default=""), token: str = Query(default=""), db=Depends(get_db),
) -> dict:
    from app.core.exceptions import NotFoundError
    from app.services.permission_service import PermissionService

    raw_token = authorization.split(" ", 1)[1] if authorization.startswith("Bearer ") else token
    if not raw_token:
        raise ForbiddenError("missing bearer token")
    payload = safe_decode_token(raw_token)
    claims = {**payload, "sub": payload.get("user_id") or payload.get("sub")}
    user_id = _require_uuid_claim(claims, "sub")
    org_id = _require_uuid_claim(claims, "org_id")
    try:
        identity = await PermissionService(db, org_id).identity(user_id)
    except NotFoundError:
        raise ForbiddenError("账号不存在或组织归属已变更，请重新登录") from None
    return {**identity, "org_id": org_id}


def apply_permission_identity(current: CurrentUser, identity) -> CurrentUser:
    if isinstance(identity, dict):
        if current.user_id != identity["user_id"] or current.org_id != identity["org_id"]:
            raise ForbiddenError("invalid token claims")
        current.role = PermissionRole(identity["role"], identity["effective"])
        current.roles = [identity["role"]]
        current.effective_permissions = identity["effective"]
        current.workspaces = derive_workspaces(current.roles, current.plan_tier)
        current.default_workspace = derive_default_workspace(current.roles, current.workspaces, current.plan_tier)
        current.capabilities = derive_capabilities(current.plan_tier, current.roles)
    return current


def get_current_user(
    authorization: str = Header(default=""), identity: dict = Depends(get_permission_identity),
) -> CurrentUser:
    if not authorization.startswith("Bearer "):
        raise ForbiddenError("missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = safe_decode_token(token)
    user_id = _require_uuid_claim(payload, "sub")
    org_id = _require_uuid_claim(payload, "org_id")
    role = payload.get("role", "")
    roles = normalize_roles(role=role, roles=payload.get("roles"))
    workspaces = payload.get("workspaces")
    if not isinstance(workspaces, list) or not workspaces:
        workspaces = derive_workspaces(roles)
    plan_tier = str(payload.get("plan_tier") or derive_plan_tier(None))
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = derive_capabilities(plan_tier, roles)
    current = CurrentUser(
        user_id=user_id,
        org_id=org_id,
        role=role,
        roles=roles,
        plan_tier=plan_tier,
        capabilities=[str(item) for item in capabilities],
        workspaces=[str(item) for item in workspaces],
        default_workspace=str(
            payload.get("default_workspace") or derive_default_workspace(roles, [str(item) for item in workspaces])
        ),
    )
    return apply_permission_identity(current, identity)
