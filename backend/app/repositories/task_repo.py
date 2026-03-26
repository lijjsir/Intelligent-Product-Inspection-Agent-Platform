from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.models.task import InspectionTask


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, task: InspectionTask) -> InspectionTask:
        self._session.add(task)
        await self._session.flush()
        await self._session.refresh(task, attribute_names=["created_at", "updated_at"])
        return task

    async def get(self, org_id: str, task_id: str) -> InspectionTask | None:
        result = await self._session.execute(
            select(InspectionTask).where(
                InspectionTask.org_id == org_id, InspectionTask.id == task_id
            )
        )
        return result.scalar_one_or_none()

    async def update_status(self, org_id: str, task_id: str, status: str) -> bool:
        values: dict = {"status": status}
        if status == "running":
            values["started_at"] = datetime.utcnow()
        if status in {"done", "failed"}:
            values["finished_at"] = datetime.utcnow()

        res = await self._session.execute(
            update(InspectionTask)
            .where(InspectionTask.org_id == org_id, InspectionTask.id == task_id)
            .values(**values)
        )
        return bool(res.rowcount and res.rowcount > 0)

    async def list_paged(self, org_id: str, filters: dict, page: int, size: int) -> tuple[list[InspectionTask], int]:
        from sqlalchemy import func
        base = (
            select(InspectionTask)
            .options(
                load_only(
                    InspectionTask.id,
                    InspectionTask.org_id,
                    InspectionTask.product_id,
                    InspectionTask.spec_code,
                    InspectionTask.status,
                    InspectionTask.priority,
                    InspectionTask.created_at,
                    InspectionTask.updated_at,
                )
            )
            .where(InspectionTask.org_id == org_id)
        )
        if "status" in filters:
            base = base.where(InspectionTask.status == filters["status"])
        if "product_id" in filters:
            base = base.where(InspectionTask.product_id == filters["product_id"])
        if "ids" in filters and filters["ids"]:
            base = base.where(InspectionTask.id.in_(filters["ids"]))

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        
        items = await self._session.execute(
            base.order_by(InspectionTask.priority.desc(), InspectionTask.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(items.scalars().all()), int(total or 0)
