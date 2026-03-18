from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics_repo import AnalyticsRepository


class AnalyticsService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = AnalyticsRepository(session)

    async def overview(self) -> dict:
        return await self._repo.get_overview(self._org_id)
