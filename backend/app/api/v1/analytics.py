from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role, ROLE_ADMIN
from app.schemas.analytics import ModelDrilldown, OverviewStats, ProductLineDrilldown, TaskDrilldown
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.analytics_service import AnalyticsService


router = APIRouter()


def _scope_org_id(current: CurrentUser) -> str | None:
    return None if ROLE_ADMIN in current.roles else current.org_id


@router.get("/overview", response_model=ResponseEnvelope[OverviewStats])
async def overview(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("analytics", current.role)
    service = AnalyticsService(db, _scope_org_id(current))
    stats = await service.overview(start_date=start_date, end_date=end_date)

    return ResponseEnvelope(data=OverviewStats(**stats))


@router.get("/product-lines/{product_line}", response_model=ResponseEnvelope[ProductLineDrilldown])
async def product_line_drilldown(
    product_line: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=8, ge=1, le=50),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("analytics", current.role)
    service = AnalyticsService(db, _scope_org_id(current))
    stats = await service.product_line_drilldown(product_line, start_date=start_date, end_date=end_date, page=page, size=size)
    return ResponseEnvelope(data=ProductLineDrilldown(**stats))


@router.get("/models/{model_key}", response_model=ResponseEnvelope[ModelDrilldown])
async def model_drilldown(
    model_key: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=8, ge=1, le=50),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("analytics", current.role)
    service = AnalyticsService(db, _scope_org_id(current))
    stats = await service.model_drilldown(model_key, start_date=start_date, end_date=end_date, page=page, size=size)
    return ResponseEnvelope(data=ModelDrilldown(**stats))


@router.get("/tasks/{task_id}", response_model=ResponseEnvelope[TaskDrilldown])
async def task_drilldown(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("analytics", current.role)
    service = AnalyticsService(db, _scope_org_id(current))
    stats = await service.task_drilldown(task_id)
    return ResponseEnvelope(data=TaskDrilldown(**stats))
