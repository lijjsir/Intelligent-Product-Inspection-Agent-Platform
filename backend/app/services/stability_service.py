from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.stability_repo import StabilityRepository


class StabilityService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = StabilityRepository(session)

    async def get_by_task(self, task_id: str):
        return await self._repo.get_by_task(self._org_id, task_id)
