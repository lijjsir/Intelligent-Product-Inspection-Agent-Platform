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
