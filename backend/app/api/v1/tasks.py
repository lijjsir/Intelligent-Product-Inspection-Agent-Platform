from fastapi import APIRouter, Depends

from app.api.v1.deps import get_db, get_current_user
from app.core.permissions import require_role
from app.schemas.common import ResponseEnvelope
from app.schemas.task import TaskCreate, TaskResponse, TaskStatusResponse, TaskListQuery
from app.schemas.user import CurrentUser
from app.services.task_service import TaskService


router = APIRouter()

@router.get("", response_model=ResponseEnvelope)
async def list_tasks(
    query: TaskListQuery = Depends(),
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("task", current.role)
    service = TaskService(db, current.org_id)
    items, total = await service.list_tasks(query)
    return ResponseEnvelope(
        data={
            "items": [TaskResponse.model_validate(t) for t in items],
            "total": total,
            "page": query.page,
            "size": query.size,
        }
    )

@router.post("", response_model=ResponseEnvelope[TaskResponse])
async def create_task(
    payload: TaskCreate,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("task", current.role)
    service = TaskService(db, current.org_id)
    task = await service.create_task(
        created_by=current.user_id,
        product_id=payload.product_id,
        spec_id=payload.spec_id,
        image_urls=payload.image_urls,
        priority=payload.priority,
        metadata=payload.metadata,
    )

    return ResponseEnvelope(
        data=TaskResponse(
            id=task.id,
            org_id=task.org_id,
            product_id=task.product_id,
            spec_id=task.spec_id,
            status=task.status,
            priority=task.priority,
        )
    )


@router.get("/{task_id}", response_model=ResponseEnvelope[TaskResponse])
async def get_task(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("task", current.role)
    service = TaskService(db, current.org_id)
    task = await service.get_task(task_id)
    if not task:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(f"Task {task_id} not found")

    return ResponseEnvelope(
        data=TaskResponse(
            id=task.id,
            org_id=task.org_id,
            product_id=task.product_id,
            spec_id=task.spec_id,
            status=task.status,
            priority=task.priority,
            created_at=task.created_at.isoformat() if task.created_at else None,
        )
    )

@router.get("/{task_id}/status", response_model=ResponseEnvelope[TaskStatusResponse])
async def get_status(
    task_id: str,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    require_role("task", current.role)
    service = TaskService(db, current.org_id)
    task = await service.get_task(task_id)

    return ResponseEnvelope(data=TaskStatusResponse(id=task.id, status=task.status))
