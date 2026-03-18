from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import InspectionTask


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, task: InspectionTask) -> InspectionTask:
        self._session.add(task)
        await self._session.flush()
        return task

    async def get(self, org_id: str, task_id: str) -> InspectionTask | None:
        result = await self._session.execute(
            select(InspectionTask).where(
                InspectionTask.org_id == org_id, InspectionTask.id == task_id
            )
        )
        return result.scalar_one_or_none()

    async def list_paged(self, org_id: str, filters: dict, page: int, size: int) -> tuple[list[InspectionTask], int]:
        from sqlalchemy import func
        base = select(InspectionTask).where(InspectionTask.org_id == org_id)
        if "status" in filters:
            base = base.where(InspectionTask.status == filters["status"])
        if "product_id" in filters:
            base = base.where(InspectionTask.product_id == filters["product_id"])

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        
        items = await self._session.execute(
            base.order_by(InspectionTask.priority.desc(), InspectionTask.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(items.scalars().all()), int(total or 0)
