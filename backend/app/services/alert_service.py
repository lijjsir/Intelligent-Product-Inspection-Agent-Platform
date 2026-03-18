from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.alert_repo import AlertRepository


class AlertService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = AlertRepository(session)

    async def get(self, alert_id: str):
        return await self._repo.get(self._org_id, alert_id)

    async def list_alerts(self, skip: int = 0, limit: int = 20, status: str | None = None, severity: str | None = None):
        return await self._repo.list_alerts(self._org_id, skip, limit, status, severity)

    async def resolve_alert(self, alert_id: str, user_id: str):
        alert = await self.get(alert_id)
        if not alert:
            return None
        await self._repo.update_status(self._org_id, alert_id, "resolved", user_id, datetime.utcnow())
        await self._session.commit()
        return True
