from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stability import StabilityReport


class StabilityRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_task(self, org_id: str, task_id: str) -> StabilityReport | None:
        result = await self._session.execute(
            select(StabilityReport).where(
                StabilityReport.org_id == org_id, StabilityReport.task_id == task_id
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
