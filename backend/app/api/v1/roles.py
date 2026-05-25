from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user
from app.core.permissions import ALL_ROLES, PERMISSIONS, require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser

router = APIRouter()

ROLE_LABELS = {
    "admin": "管理员",
    "app_developer": "应用开发者",
    "platform_operator": "平台运营",
    "algorithm_engineer": "算法工程师",
    "user": "普通用户",
    "expert": "领域专家",
}


@router.get("", response_model=ResponseEnvelope[list[dict[str, str]]])
async def list_roles(current: CurrentUser = Depends(get_current_user)):
    require_role("role_read", current.role)
    data = [{"key": role, "label": ROLE_LABELS.get(role, role)} for role in sorted(ALL_ROLES)]
    return ResponseEnvelope(data=data)


@router.get("/permissions", response_model=ResponseEnvelope[dict])
async def get_permissions_matrix(current: CurrentUser = Depends(get_current_user)):
    require_role("role_read", current.role)
    roles = sorted(ALL_ROLES)
    resources = sorted(PERMISSIONS.keys())
    matrix = {role: [resource for resource in resources if role in PERMISSIONS.get(resource, set())] for role in roles}
    return ResponseEnvelope(data={"resources": resources, "matrix": matrix})
