from fastapi import Depends, Header
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


def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    if not authorization.startswith("Bearer "):
        raise ForbiddenError("missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = safe_decode_token(token)
    role = payload.get("role", "")
    roles = normalize_roles(role=role, roles=payload.get("roles"))
    workspaces = payload.get("workspaces")
    if not isinstance(workspaces, list) or not workspaces:
        workspaces = derive_workspaces(roles)
    plan_tier = str(payload.get("plan_tier") or derive_plan_tier(None))
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = derive_capabilities(plan_tier, roles)
    return CurrentUser(
        user_id=payload.get("sub", ""),
        org_id=payload.get("org_id", ""),
        role=role,
        roles=roles,
        plan_tier=plan_tier,
        capabilities=[str(item) for item in capabilities],
        workspaces=[str(item) for item in workspaces],
        default_workspace=str(
            payload.get("default_workspace") or derive_default_workspace(roles, [str(item) for item in workspaces])
        ),
    )
