from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role, ROLE_ADMIN
from app.schemas.common import ResponseEnvelope
from app.schemas.governance import QualityReportResponse, QualityTraceItem, QualityTraceListResponse
from app.schemas.user import CurrentUser
from app.services.quality_report_service import QualityReportService


router = APIRouter()


def _scope_org_id(current: CurrentUser) -> str | None:
    return None if ROLE_ADMIN in current.roles else current.org_id


@router.get("/report", response_model=ResponseEnvelope[QualityReportResponse])
async def get_quality_report(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    source: str = Query(default="all", pattern="^(all|inspection|chat)$"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("quality", current.role)
    service = QualityReportService(db, _scope_org_id(current))
    data = await service.build_report(
        start_date=None if not start_date else __import__("datetime").date.fromisoformat(start_date),
        end_date=None if not end_date else __import__("datetime").date.fromisoformat(end_date),
        source=source,
    )
    return ResponseEnvelope(data=QualityReportResponse(**data))


@router.get("/traces", response_model=ResponseEnvelope[QualityTraceListResponse])
async def list_quality_traces(
    limit: int = Query(default=100, ge=1, le=500),
    source: str = Query(default="all", pattern="^(all|inspection|chat)$"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("quality", current.role)
    service = QualityReportService(db, _scope_org_id(current))
    result = await service.list_traces_with_meta(limit=limit, source=source)
    return ResponseEnvelope(
        data=QualityTraceListResponse(
            items=[QualityTraceItem(**item) for item in result["items"]],
            meta=result["meta"],
        )
    )


@router.delete("/traces/{trace_id}", response_model=ResponseEnvelope[dict])
async def delete_quality_trace(
    trace_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("quality", current.role)
    service = QualityReportService(db, _scope_org_id(current))
    result = await service.delete_trace(trace_id)
    return ResponseEnvelope(data=result)
