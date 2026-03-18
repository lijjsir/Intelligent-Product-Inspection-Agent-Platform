from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.tool import ToolCreate, ToolResponse
from app.schemas.user import CurrentUser
from app.services.tool_service import ToolService


router = APIRouter()


@router.post("", response_model=ResponseEnvelope[ToolResponse])
async def create_tool(
    payload: ToolCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolService(db, current.org_id)
    tool = await service.create_tool(payload.model_dump())

    return ResponseEnvelope(
        data=ToolResponse(
            id=tool.id,
            name=tool.name,
            display_name=tool.display_name,
            is_active=tool.is_active,
        )
    )
