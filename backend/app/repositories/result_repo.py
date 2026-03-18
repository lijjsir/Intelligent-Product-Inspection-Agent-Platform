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
