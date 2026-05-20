from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.prompt_admin import (
    CreateVersionRequest,
    DiffResponse,
    PromptDefinitionDetail,
    PromptDefinitionSummary,
    PromptOverviewResponse,
    RollbackRequest,
    SyncScanResponse,
)
from app.schemas.user import CurrentUser
from app.services.prompt_admin_service import PromptAdminService

router = APIRouter(prefix="/prompt-admin", tags=["Prompt Admin"])


def _svc(current: CurrentUser, db) -> PromptAdminService:
    require_role("prompt_admin", current.role)
    return PromptAdminService(db, current.org_id, current.user_id)


@router.get("/overview", response_model=ResponseEnvelope[PromptOverviewResponse])
async def get_overview(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _svc(current, db)
    return ResponseEnvelope(data=await svc.overview())


@router.get("/definitions", response_model=ResponseEnvelope[list[PromptDefinitionSummary]])
async def list_definitions(
    agent_key: str | None = Query(default=None),
    stage_key: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    sync_status: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _svc(current, db)
    items = await svc.list_definitions(
        agent_key=agent_key, stage_key=stage_key, keyword=keyword, sync_status=sync_status
    )
    return ResponseEnvelope(data=items)


# Sub-resource routes MUST be registered before the generic {prompt_key} detail route
# to prevent Starlette from greedily capturing /diff, /versions, /rollback suffixes.


@router.get("/definitions/{prompt_key}/diff", response_model=ResponseEnvelope[DiffResponse])
async def diff_definition(
    prompt_key: str,
    left: str = Query(default="code_default"),
    right: str = Query(default="active"),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _svc(current, db)
    try:
        result = await svc.diff(prompt_key, left=left, right=right)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseEnvelope(data=result)


@router.post("/definitions/{prompt_key}/versions", response_model=ResponseEnvelope[dict], status_code=201)
async def create_version(
    prompt_key: str,
    body: CreateVersionRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _svc(current, db)
    try:
        result = await svc.create_version(
            prompt_key, content=body.content, change_summary=body.change_summary, base_hash=body.base_hash
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseEnvelope(data=result)


@router.post("/definitions/{prompt_key}/rollback", response_model=ResponseEnvelope[dict])
async def rollback_definition(
    prompt_key: str,
    body: RollbackRequest,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _svc(current, db)
    try:
        result = await svc.rollback(prompt_key, body.target_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseEnvelope(data=result)


@router.get("/definitions/{prompt_key}", response_model=ResponseEnvelope[PromptDefinitionDetail])
async def get_definition(
    prompt_key: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _svc(current, db)
    detail = await svc.get_definition_detail(prompt_key)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Prompt definition not found: {prompt_key}")
    return ResponseEnvelope(data=detail)


@router.post("/versions/{version_id}/publish", response_model=ResponseEnvelope[dict])
async def publish_version(
    version_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _svc(current, db)
    try:
        result = await svc.publish_version(version_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseEnvelope(data=result)


@router.post("/sync/scan", response_model=ResponseEnvelope[SyncScanResponse])
async def scan_code_prompts(
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    svc = _svc(current, db)
    result = await svc.scan_code_prompts()
    return ResponseEnvelope(data=result)
