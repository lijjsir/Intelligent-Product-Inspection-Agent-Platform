from fastapi import APIRouter, Depends, status

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.inspection_standard_library import (
    InspectionStandardCreate,
    InspectionStandardResponse,
    InspectionStandardUpdate,
)
from app.schemas.user import CurrentUser
from app.services.inspection_standard_library_service import InspectionStandardLibraryService

router = APIRouter()


@router.get("", response_model=ResponseEnvelope[list[InspectionStandardResponse]])
async def list_inspection_standards(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_items())


@router.get("/{library_id}", response_model=ResponseEnvelope[InspectionStandardResponse])
async def get_inspection_standard(
    library_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.get_item(library_id))


@router.post("", response_model=ResponseEnvelope[InspectionStandardResponse], status_code=status.HTTP_201_CREATED)
async def create_inspection_standard(
    payload: InspectionStandardCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_item(payload.model_dump()))


@router.patch("/{library_id}", response_model=ResponseEnvelope[InspectionStandardResponse])
async def update_inspection_standard(
    library_id: str,
    payload: InspectionStandardUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_item(library_id, payload.model_dump(exclude_unset=True)))


@router.delete("/{library_id}", response_model=ResponseEnvelope[dict[str, bool]])
async def delete_inspection_standard(
    library_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("inspection_standard_library", current.role)
    service = InspectionStandardLibraryService(db, current.org_id)
    await service.delete_item(library_id)
    return ResponseEnvelope(data={"success": True})
