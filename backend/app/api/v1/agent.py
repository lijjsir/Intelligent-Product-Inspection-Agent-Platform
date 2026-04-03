from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from app.api.v1.deps import get_current_user, get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import require_role
from app.core.security import safe_decode_token
from app.repositories.task_repo import TaskRepository
from app.schemas.common import ResponseEnvelope
from app.schemas.user import CurrentUser
from app.services.inspection_pipeline_service import run_inspection_pipeline
from app.services.stream_service import stream_broker
from worker.tasks.inspection_task import run_inspection


router = APIRouter()


def get_current_user_for_sse(
    authorization: str = Header(default=""),
    token: str = Query(default=""),
) -> CurrentUser:
    """为 SSE 长连接请求解析当前用户，兼容请求头和查询参数两种令牌传递方式。"""
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
    )


@router.post("/tasks/{task_id}/run", response_model=ResponseEnvelope[dict])
async def run_task_pipeline(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """启动指定任务的 AI 检测流水线，优先投递到 Celery，失败时回退到本地后台执行。"""
    require_role("task", current.role)
    task = await TaskRepository(db).get(current.org_id, task_id)
    if not task:
        raise NotFoundError("task not found")

    payload = {"task_id": task_id, "org_id": current.org_id}
    try:
        async_result = run_inspection.delay(payload)
        data = {"mode": "celery", "job_id": async_result.id}
    except Exception:
        # Fallback for local dev when celery worker is not running.
        asyncio.create_task(run_inspection_pipeline(task_id=task_id, org_id=current.org_id))
        data = {"mode": "local_background", "job_id": None}
    return ResponseEnvelope(data=data)


@router.get("/tasks/{task_id}/stream")
async def stream_task_events(
    task_id: str,
    current: CurrentUser = Depends(get_current_user_for_sse),
    db=Depends(get_db),
) -> StreamingResponse:
    """通过 SSE 持续向前端推送任务状态变化和图执行阶段事件。"""
    require_role("task", current.role)
    task = await TaskRepository(db).get(current.org_id, task_id)
    if not task:
        raise NotFoundError("task not found")

    async def event_iter() -> AsyncIterator[str]:
        """按 SSE 协议格式输出历史事件和后续实时事件。"""
        yield "event: ready\ndata: {\"message\":\"stream_connected\"}\n\n"
        async for event in stream_broker.subscribe(task_id):
            payload = json.dumps(event, ensure_ascii=False)
            yield f"event: message\ndata: {payload}\n\n"

    return StreamingResponse(event_iter(), media_type="text/event-stream")
