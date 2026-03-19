from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.result import InspectionResult


class ResultRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_task(self, org_id: str, task_id: str) -> InspectionResult | None:
        result = await self._session.execute(
            select(InspectionResult).where(
                InspectionResult.org_id == org_id, InspectionResult.task_id == task_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert_by_task(self, payload: dict) -> InspectionResult:
        existing = await self.get_by_task(payload["org_id"], payload["task_id"])
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
            await self._session.flush()
            return existing

        obj = InspectionResult(**payload)
        self._session.add(obj)
        await self._session.flush()
        return obj
