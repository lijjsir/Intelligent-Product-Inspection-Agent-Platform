from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.alert_repo import AlertRepository


class AlertService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = AlertRepository(session)

    async def get(self, alert_id: str):
        return await self._repo.get(self._org_id, alert_id)
