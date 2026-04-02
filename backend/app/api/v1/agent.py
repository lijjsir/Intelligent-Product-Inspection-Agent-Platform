from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from app.api.v1.deps import get_current_user, get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import ROLE_ADMIN, ROLE_USER, normalize_role, require_role
from app.core.security import safe_decode_token
from app.repositories.task_repo import TaskRepository
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.task_execution_service import launch_task_execution
from app.services.stream_service import stream_broker


router = APIRouter()


def get_current_user_for_sse(
    authorization: str = Header(default=""),
    token: str = Query(default=""),
) -> CurrentUser:
    if authorization.startswith("Bearer "):
        payload = safe_decode_token(authorization.split(" ", 1)[1])
    elif token:
        payload = safe_decode_token(token)
    else:
        raise ForbiddenError("missing bearer token")
    return CurrentUser(
        user_id=payload.get("sub", ""),
        org_id=payload.get("org_id", ""),
        role=payload.get("role", ""),
        roles=[str(item) for item in (payload.get("roles") or [])],
        plan_tier=str(payload.get("plan_tier") or "basic"),
        capabilities=[str(item) for item in (payload.get("capabilities") or [])],
        workspaces=[str(item) for item in (payload.get("workspaces") or [])],
        default_workspace=str(payload.get("default_workspace") or "app"),
        stream_resource=str(payload.get("resource") or ""),
        stream_resource_id=str(payload.get("resource_id") or ""),
    )


@router.post("/tasks/{task_id}/run", response_model=ResponseEnvelope[dict])
async def run_task_pipeline(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("task", current.role)
    normalized_role = normalize_role(current.role)
    owner_user_id = current.user_id if normalized_role == ROLE_USER else None
    org_scope = None if normalized_role == ROLE_ADMIN else current.org_id
    task = await TaskRepository(db).get_for_user(org_scope, task_id, owner_user_id=owner_user_id)
    if not task:
        raise NotFoundError("task not found")

    data = await launch_task_execution(task_id=task_id, org_id=current.org_id)
    return ResponseEnvelope(data=data)


@router.get("/tasks/{task_id}/stream")
async def stream_task_events(
    task_id: str,
    current: CurrentUser = Depends(get_current_user_for_sse),
    db=Depends(get_db),
) -> StreamingResponse:
    require_role("task", current.role)
    if current.stream_resource and (
        current.stream_resource != "task" or current.stream_resource_id != task_id
    ):
        raise ForbiddenError("invalid stream token")
    normalized_role = normalize_role(current.role)
    owner_user_id = current.user_id if normalized_role == ROLE_USER else None
    org_scope = None if normalized_role == ROLE_ADMIN else current.org_id
    task = await TaskRepository(db).get_for_user(org_scope, task_id, owner_user_id=owner_user_id)
    if not task:
        raise NotFoundError("task not found")

    async def event_iter() -> AsyncIterator[str]:
        yield "event: ready\ndata: {\"message\":\"stream_connected\"}\n\n"
        async for event in stream_broker.subscribe(task_id):
            payload = json.dumps(event, ensure_ascii=False)
            yield f"event: message\ndata: {payload}\n\n"

    return StreamingResponse(event_iter(), media_type="text/event-stream")
