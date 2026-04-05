from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stability import StabilityReport
from app.models.task import InspectionTask


class StabilityRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_task(self, org_id: str, task_id: str) -> StabilityReport | None:
        result = await self._session.execute(
            select(StabilityReport)
            .join(InspectionTask, InspectionTask.id == StabilityReport.task_id)
            .where(
                StabilityReport.org_id == org_id,
                StabilityReport.task_id == task_id,
                InspectionTask.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_by_task(self, payload: dict) -> StabilityReport:
        existing = await self.get_by_task(payload["org_id"], payload["task_id"])
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
            await self._session.flush()
            return existing

        obj = StabilityReport(**payload)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def list_by_range(self, org_id: str | None, start_date=None, end_date=None) -> list[StabilityReport]:
        stmt = (
            select(StabilityReport)
            .join(InspectionTask, InspectionTask.id == StabilityReport.task_id)
            .where(InspectionTask.deleted_at.is_(None))
        )
        if org_id:
            stmt = stmt.where(StabilityReport.org_id == org_id, InspectionTask.org_id == org_id)
        if start_date:
            stmt = stmt.where(StabilityReport.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            stmt = stmt.where(StabilityReport.created_at <= datetime.combine(end_date, datetime.max.time()))
        result = await self._session.execute(stmt.order_by(StabilityReport.created_at.asc()))
        return list(result.scalars().all())
