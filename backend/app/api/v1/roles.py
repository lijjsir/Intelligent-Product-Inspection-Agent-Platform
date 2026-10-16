from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import ROLE_DISPLAY_ORDER, ROLE_LABELS, require_role
from app.schemas.permission import RolePermissionUpdate
from app.services.permission_service import PermissionService
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser

router = APIRouter()


@router.get("", response_model=ResponseEnvelope[list[dict[str, str]]])
async def list_roles(current: CurrentUser = Depends(get_current_user)):
    require_role("role_read", current.role)
    data = [{"key": role, "label": ROLE_LABELS.get(role, role)} for role in ROLE_DISPLAY_ORDER]
    return ResponseEnvelope(data=data)


@router.get("/permissions", response_model=ResponseEnvelope[dict])
async def get_permissions_matrix(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    require_role("role_read", current.role)
    return ResponseEnvelope(data=await PermissionService(db, current.org_id).matrix())


@router.put("/{role}/permissions", response_model=ResponseEnvelope[dict])
async def update_role_permissions(
    role: str, payload: RolePermissionUpdate,
    current: CurrentUser = Depends(get_current_user), db=Depends(get_db),
):
    return ResponseEnvelope(data=await PermissionService(db, current.org_id).save_role(role, payload, current))
