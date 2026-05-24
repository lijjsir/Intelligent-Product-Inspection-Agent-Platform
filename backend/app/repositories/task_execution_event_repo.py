from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_execution_event import TaskExecutionEvent


class TaskExecutionEventRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, payload: dict) -> TaskExecutionEvent:
        event = TaskExecutionEvent(**payload)
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_by_task(
        self,
        org_id: str,
        task_id: str,
        *,
        limit: int = 200,
    ) -> list[TaskExecutionEvent]:
        result = await self._session.execute(
            select(TaskExecutionEvent)
            .where(
                TaskExecutionEvent.org_id == org_id,
                TaskExecutionEvent.task_id == task_id,
            )
            .order_by(TaskExecutionEvent.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_after(
        self,
        org_id: str,
        task_id: str,
        *,
        after_id: str | None = None,
        limit: int = 50,
    ) -> list[TaskExecutionEvent]:
        stmt = select(TaskExecutionEvent).where(
            TaskExecutionEvent.org_id == org_id,
            TaskExecutionEvent.task_id == task_id,
        )
        if after_id:
            stmt = stmt.where(TaskExecutionEvent.id > after_id)
        result = await self._session.execute(
            stmt.order_by(TaskExecutionEvent.id.asc()).limit(limit)
        )
        return list(result.scalars().all())
