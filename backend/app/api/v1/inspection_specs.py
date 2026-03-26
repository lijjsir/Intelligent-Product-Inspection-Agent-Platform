from fastapi import APIRouter, Depends, status

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.inspection_spec import InspectionSpecCreate, InspectionSpecResponse, InspectionSpecUpdate
from app.schemas.user import CurrentUser
from app.services.inspection_spec_service import InspectionSpecService


router = APIRouter()


@router.get("", response_model=ResponseEnvelope[list[InspectionSpecResponse]])
async def list_inspection_specs(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_spec", current.role)
    service = InspectionSpecService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_specs())


@router.get("/{inspection_spec_row_id}", response_model=ResponseEnvelope[InspectionSpecResponse])
async def get_inspection_spec(
    inspection_spec_row_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_spec", current.role)
    service = InspectionSpecService(db, current.org_id)
    return ResponseEnvelope(data=await service.get_spec(inspection_spec_row_id))


@router.post("", response_model=ResponseEnvelope[InspectionSpecResponse], status_code=status.HTTP_201_CREATED)
async def create_inspection_spec(
    payload: InspectionSpecCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_spec", current.role)
    service = InspectionSpecService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_spec(payload.model_dump(), current.role))


@router.patch("/{inspection_spec_row_id}", response_model=ResponseEnvelope[InspectionSpecResponse])
async def update_inspection_spec(
    inspection_spec_row_id: str,
    payload: InspectionSpecUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_spec", current.role)
    service = InspectionSpecService(db, current.org_id)
    return ResponseEnvelope(
        data=await service.update_spec(
            inspection_spec_row_id,
            payload.model_dump(exclude_unset=True),
            current.role,
        )
    )


@router.delete("/{inspection_spec_row_id}", response_model=ResponseEnvelope[bool])
async def delete_inspection_spec(
    inspection_spec_row_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_spec", current.role)
    service = InspectionSpecService(db, current.org_id)
    await service.delete_spec(inspection_spec_row_id, current.role)
    return ResponseEnvelope(data=True)
