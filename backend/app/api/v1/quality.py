from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.governance import QualityReportResponse, QualityTraceItem
from app.schemas.user import CurrentUser
from app.services.quality_report_service import QualityReportService


router = APIRouter()


@router.get("/report", response_model=ResponseEnvelope[QualityReportResponse])
async def get_quality_report(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("quality", current.role)
    service = QualityReportService(db, current.org_id)
    data = await service.build_report(
        start_date=None if not start_date else __import__("datetime").date.fromisoformat(start_date),
        end_date=None if not end_date else __import__("datetime").date.fromisoformat(end_date),
    )
    return ResponseEnvelope(data=QualityReportResponse(**data))


@router.get("/traces", response_model=ResponseEnvelope[list[QualityTraceItem]])
async def list_quality_traces(
    limit: int = Query(default=100, ge=1, le=500),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("quality", current.role)
    service = QualityReportService(db, current.org_id)
    data = await service.list_traces(limit=limit)
    return ResponseEnvelope(data=[QualityTraceItem(**item) for item in data])
