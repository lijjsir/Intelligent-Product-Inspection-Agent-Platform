import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.models.tool import ToolRuntimeEvent
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.tool import (
    AgentToolBindingResponse,
    BindingCreate,
    BindingUpdate,
    ToolCreate,
    ToolDetailResponse,
    ToolExecutionListQuery,
    ToolExecutionOverviewResponse,
    ToolExecutionResponse,
    ToolListQuery,
    ToolOverviewResponse,
    ToolResponse,
    ToolStatusUpdate,
    ToolTestRequest,
    ToolTestResultResponse,
    ToolUpdate,
    ToolVersionCreate,
    ToolVersionResponse,
)
from app.schemas.user import CurrentUser
from app.services.tool_binding_service import ToolBindingService
from app.services.tool_import_service import ToolImportService
from app.services.tool_service import ToolService
from app.services.tool_sync_service import ToolSyncService
from app.services.tool_version_service import ToolVersionService


router = APIRouter()


@router.get("/overview", response_model=ResponseEnvelope[ToolOverviewResponse])
async def get_tool_overview(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolService(db, current.org_id)
    return ResponseEnvelope(data=await service.get_overview())


@router.get("", response_model=ResponseEnvelope[PagedResponse[ToolResponse]])
async def list_tools(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=12, ge=1, le=200),
    keyword: str | None = None,
    category: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    risk_level: str | None = None,
    has_binding: bool | None = None,
    source_type: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    query = ToolListQuery(
        page=page,
        size=size,
        keyword=keyword,
        category=category,
        status=status_filter,
        risk_level=risk_level,
        has_binding=has_binding,
        source_type=source_type,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    service = ToolService(db, current.org_id)
    return ResponseEnvelope(data=PagedResponse[ToolResponse](**await service.list_tools(query.model_dump())))


@router.get("/executions/overview", response_model=ResponseEnvelope[ToolExecutionOverviewResponse])
async def get_execution_overview(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolService(db, current.org_id)
    return ResponseEnvelope(data=await service.get_execution_overview())


@router.get("/executions", response_model=ResponseEnvelope[PagedResponse[ToolExecutionResponse]])
async def list_executions(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    tool_id: str | None = None,
    agent_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    execution_type: str | None = None,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    query = ToolExecutionListQuery(
        page=page,
        size=size,
        tool_id=tool_id,
        agent_id=agent_id,
        status=status_filter,
        execution_type=execution_type,
    )
    service = ToolService(db, current.org_id)
    return ResponseEnvelope(
        data=PagedResponse[ToolExecutionResponse](**await service.list_executions(query.model_dump()))
    )


@router.get("/bindings", response_model=ResponseEnvelope[list[AgentToolBindingResponse]])
async def get_bindings(
    tool_id: str | None = None,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolBindingService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_bindings(tool_id=tool_id))


@router.post("/bindings", response_model=ResponseEnvelope[AgentToolBindingResponse], status_code=http_status.HTTP_201_CREATED)
async def create_binding(
    payload: BindingCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolBindingService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_binding(payload.model_dump()))


@router.put("/bindings/{binding_id}", response_model=ResponseEnvelope[AgentToolBindingResponse])
async def update_binding(
    binding_id: str,
    payload: BindingUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolBindingService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_binding(binding_id, payload.model_dump(exclude_unset=True)))


@router.delete("/bindings/{binding_id}", response_model=ResponseEnvelope[object])
async def delete_binding(
    binding_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolBindingService(db, current.org_id)
    return ResponseEnvelope(data=await service.delete_binding(binding_id))


@router.post("/sync/builtin", response_model=ResponseEnvelope[object])
async def sync_builtin_tools(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolSyncService(db, current.org_id)
    result = await service.scan_and_sync()
    return ResponseEnvelope(data=result)


@router.post("/import/openapi/preview", response_model=ResponseEnvelope[object])
async def preview_openapi_import(
    payload: dict,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolImportService(db, current.org_id)
    candidates = await service.preview_openapi(payload.get("source", ""))
    return ResponseEnvelope(data={"candidates": candidates, "total": len(candidates)})


@router.post("/import/openapi", response_model=ResponseEnvelope[object])
async def import_openapi_tools(
    payload: dict,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolImportService(db, current.org_id)
    imported = await service.import_openapi_tools(
        payload.get("source", ""),
        payload.get("tool_keys", []),
    )
    return ResponseEnvelope(data={"imported": imported})


@router.post("/import/mcp/preview", response_model=ResponseEnvelope[object])
async def preview_mcp_import(
    payload: dict,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolImportService(db, current.org_id)
    candidates = await service.preview_mcp_tools(payload.get("server_url", ""))
    return ResponseEnvelope(data={"candidates": candidates, "total": len(candidates)})


@router.get("/events/stream")
async def tool_events_stream(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)

    async def event_generator():
        last_event_id = ""
        while True:
            try:
                result = await db.execute(
                    select(ToolRuntimeEvent)
                    .where(ToolRuntimeEvent.org_id == current.org_id)
                    .order_by(ToolRuntimeEvent.created_at.desc())
                    .limit(50)
                )
                events = result.scalars().all()
                for event in reversed(events):
                    if event.id > last_event_id:
                        yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(event.payload or {})}\n\n"
                        last_event_id = event.id
                await asyncio.sleep(5)
            except Exception:
                await asyncio.sleep(10)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("", response_model=ResponseEnvelope[ToolResponse], status_code=http_status.HTTP_201_CREATED)
async def create_tool(
    payload: ToolCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolService(db, current.org_id)
    tool = await service.create_tool(payload.model_dump())
    return ResponseEnvelope(data=await service.get_tool_detail(tool.id))


@router.get("/{tool_id}", response_model=ResponseEnvelope[ToolDetailResponse])
async def get_tool_detail(
    tool_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolService(db, current.org_id)
    return ResponseEnvelope(data=await service.get_tool_detail(tool_id))


@router.put("/{tool_id}", response_model=ResponseEnvelope[ToolResponse])
async def update_tool(
    tool_id: str,
    payload: ToolUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_tool(tool_id, payload.model_dump(exclude_unset=True)))


@router.patch("/{tool_id}/status", response_model=ResponseEnvelope[ToolResponse])
async def update_tool_status(
    tool_id: str,
    payload: ToolStatusUpdate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolService(db, current.org_id)
    return ResponseEnvelope(data=await service.update_tool_status(tool_id, payload.status))


@router.get("/{tool_id}/versions", response_model=ResponseEnvelope[list[ToolVersionResponse]])
async def list_tool_versions(
    tool_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolVersionService(db, current.org_id)
    return ResponseEnvelope(data=await service.list_versions(tool_id))


@router.post("/{tool_id}/test", response_model=ResponseEnvelope[ToolTestResultResponse])
async def test_tool(
    tool_id: str,
    payload: ToolTestRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolService(db, current.org_id)
    return ResponseEnvelope(data=await service.test_tool(tool_id, payload.params))


@router.post("/{tool_id}/versions", response_model=ResponseEnvelope[ToolVersionResponse], status_code=http_status.HTTP_201_CREATED)
async def create_tool_version(
    tool_id: str,
    payload: ToolVersionCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolVersionService(db, current.org_id)
    return ResponseEnvelope(data=await service.create_version(tool_id, payload.model_dump(exclude_unset=True)))


@router.post("/{tool_id}/versions/{version_id}/publish", response_model=ResponseEnvelope[object])
async def publish_version(
    tool_id: str,
    version_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolVersionService(db, current.org_id)
    return ResponseEnvelope(data=await service.publish_version(tool_id, version_id))


@router.post("/{tool_id}/versions/{version_id}/rollback", response_model=ResponseEnvelope[object])
async def rollback_version(
    tool_id: str,
    version_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("tool", current.role)
    service = ToolVersionService(db, current.org_id)
    return ResponseEnvelope(data=await service.rollback_version(tool_id, version_id))
