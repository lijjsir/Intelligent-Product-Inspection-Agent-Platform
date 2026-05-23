from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    OrganizationUserAssignRequest,
    OrganizationUserItem,
    OrganizationUsersResponse,
)
from app.schemas.user import CurrentUser
from app.services.organization_service import OrganizationService

router = APIRouter()


def _to_org_response(org, user_count: int = 0) -> OrganizationResponse:
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        settings=org.settings,
        is_active=org.is_active,
        created_at=org.created_at,
        updated_at=org.updated_at,
        user_count=user_count,
    )


@router.get("", response_model=ResponseEnvelope[list[OrganizationResponse]])
async def list_organizations(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("organization", current.role)
    service = OrganizationService(db)
    rows = await service.list_organizations()
    return ResponseEnvelope(data=[_to_org_response(org, user_count) for org, user_count in rows])


@router.post("", response_model=ResponseEnvelope[OrganizationResponse])
async def create_organization(
    payload: OrganizationCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("organization", current.role)
    service = OrganizationService(db)
    org = await service.create_organization(payload)
    await db.refresh(org)
    return ResponseEnvelope(data=_to_org_response(org))


@router.patch("/{org_id}", response_model=ResponseEnvelope[OrganizationResponse])
async def update_organization(
    org_id: str,
    payload: OrganizationUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("organization", current.role)
    service = OrganizationService(db)
    org = await service.update_organization(org_id, payload)
    await db.refresh(org)
    return ResponseEnvelope(data=_to_org_response(org))


@router.delete("/{org_id}", response_model=ResponseEnvelope[dict[str, bool]])
async def delete_organization(
    org_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("organization", current.role)
    service = OrganizationService(db)
    await service.delete_organization(org_id)
    return ResponseEnvelope(data={"success": True})


@router.get("/{org_id}/users", response_model=ResponseEnvelope[OrganizationUsersResponse])
async def get_organization_users(
    org_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("organization", current.role)
    service = OrganizationService(db)
    org, users = await service.get_organization_users(org_id)
    return ResponseEnvelope(
        data=OrganizationUsersResponse(
            organization={"id": org.id, "name": org.name},
            users=[
                OrganizationUserItem(
                    id=user.id,
                    username=user.username,
                    role=user.role,
                    is_active=user.is_active,
                )
                for user in users
            ],
            total=len(users),
        )
    )


@router.post("/{org_id}/users", response_model=ResponseEnvelope[dict[str, int]])
async def assign_organization_users(
    org_id: str,
    payload: OrganizationUserAssignRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("organization", current.role)
    service = OrganizationService(db)
    affected = await service.assign_users(org_id, payload.user_ids, payload.action)
    return ResponseEnvelope(data={"affected": affected})
