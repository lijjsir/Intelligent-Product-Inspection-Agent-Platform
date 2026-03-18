from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role
from app.schemas.analytics import OverviewStats
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.analytics_service import AnalyticsService


router = APIRouter()


@router.get("/overview", response_model=ResponseEnvelope[OverviewStats])
async def overview(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("analytics", current.role)
    service = AnalyticsService(db, current.org_id)
    stats = await service.overview()

    return ResponseEnvelope(data=OverviewStats(**stats))
