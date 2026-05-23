from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.infrastructure import InfrastructureStatusResponse
from app.schemas.user import CurrentUser
from app.services.infrastructure_service import InfrastructureService

router = APIRouter()


@router.get("/status", response_model=ResponseEnvelope[InfrastructureStatusResponse])
async def get_infrastructure_status(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("infrastructure", current.role)
    service = InfrastructureService(db)
    return ResponseEnvelope(data=await service.check_all())


@router.post("/check-all", response_model=ResponseEnvelope[InfrastructureStatusResponse])
async def check_all_infrastructure(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("infrastructure", current.role)
    service = InfrastructureService(db)
    return ResponseEnvelope(data=await service.check_all())
