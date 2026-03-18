from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role
from app.schemas.alert import AlertResponse
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.alert_service import AlertService


router = APIRouter()


@router.get("/{alert_id}", response_model=ResponseEnvelope[AlertResponse])
async def get_alert(
    alert_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("alert", current.role)
    service = AlertService(db, current.org_id)
    alert = await service.get(alert_id)

    return ResponseEnvelope(
        data=AlertResponse(
            id=alert.id,
            org_id=alert.org_id,
            severity=alert.severity,
            status=alert.status,
            title=alert.title,
        )
    )
