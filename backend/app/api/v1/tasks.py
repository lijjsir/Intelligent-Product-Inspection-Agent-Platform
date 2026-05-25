from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.exceptions import NotFoundError
from app.core.permissions import require_role
from app.repositories.task_execution_event_repo import TaskExecutionEventRepository
from app.schemas.common import PagedResponse, ResponseEnvelope
from app.schemas.task import (
    TaskCreate,
    TaskExecutionEventResponse,
    TaskListItemResponse,
    TaskListQuery,
    TaskResponse,
    TaskStatusResponse,
)
from app.schemas.user import CurrentUser
from app.services.task_service import TaskService


router = APIRouter()


@router.get("", response_model=ResponseEnvelope[PagedResponse[TaskListItemResponse]])
async def list_tasks(
    query: TaskListQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """返回任务管理页需要的分页任务列表。"""
    require_role("task", current.role)
    service = TaskService(
        db,
        current.org_id,
        actor_user_id=current.user_id,
        actor_role=current.role,
    )
    items, total = await service.list_tasks(query)
    return ResponseEnvelope(
        data=PagedResponse(
            items=[TaskListItemResponse.model_validate(t) for t in items],
            total=total,
            page=query.page,
            size=query.size,
        )
    )

@router.post("", response_model=ResponseEnvelope[TaskResponse])
async def create_task(
    payload: TaskCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """校验检测标准后创建待执行的质检任务。"""
    require_role("task", current.role)
    service = TaskService(db, current.org_id)
    task = await service.create_task(
        created_by=current.user_id,
        product_id=payload.product_id,
        spec_code=payload.spec_code,
        image_urls=payload.image_urls,
        image_items=payload.image_items,
        priority=payload.priority,
        metadata=payload.metadata,
    )

    return ResponseEnvelope(data=TaskResponse.model_validate(task))


@router.get("/{task_id}", response_model=ResponseEnvelope[TaskResponse])
async def get_task(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """返回任务详情页展示和运行态刷新所需的单个任务数据。"""
    require_role("task", current.role)
    service = TaskService(
        db,
        current.org_id,
        actor_user_id=current.user_id,
        actor_role=current.role,
    )
    task = await service.get_task(task_id)
    if not task:
        raise NotFoundError(f"Task {task_id} not found")

    return ResponseEnvelope(data=TaskResponse.model_validate(task))

@router.get("/{task_id}/status", response_model=ResponseEnvelope[TaskStatusResponse])
async def get_status(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    """返回任务的最新状态，供轻量轮询场景使用。"""
    require_role("task", current.role)
    service = TaskService(
        db,
        current.org_id,
        actor_user_id=current.user_id,
        actor_role=current.role,
    )
    task = await service.get_task(task_id)
    if not task:
        raise NotFoundError(f"Task {task_id} not found")

    return ResponseEnvelope(data=TaskStatusResponse(id=task.id, status=task.status))


@router.get("/{task_id}/events", response_model=ResponseEnvelope[list[TaskExecutionEventResponse]])
async def get_task_events(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("task", current.role)
    service = TaskService(
        db,
        current.org_id,
        actor_user_id=current.user_id,
        actor_role=current.role,
    )
    task = await service.get_task(task_id)
    if not task:
        raise NotFoundError(f"Task {task_id} not found")

    repo = TaskExecutionEventRepository(db)
    events = await repo.list_by_task(str(task.org_id), task_id)
    return ResponseEnvelope(data=[TaskExecutionEventResponse.model_validate(item) for item in events])


@router.delete("/{task_id}", response_model=ResponseEnvelope[dict])
async def delete_task(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("task", current.role)
    service = TaskService(
        db,
        current.org_id,
        actor_user_id=current.user_id,
        actor_role=current.role,
    )
    task = await service.delete_task(task_id)
    if not task:
        raise NotFoundError(f"Task {task_id} not found")
    await db.commit()
    return ResponseEnvelope(data={"deleted": True, "task_id": task_id})
