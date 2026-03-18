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
