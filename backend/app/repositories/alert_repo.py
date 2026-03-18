from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertEvent


class AlertRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, org_id: str, alert_id: str) -> AlertEvent | None:
        result = await self._session.execute(
            select(AlertEvent).where(AlertEvent.org_id == org_id, AlertEvent.id == alert_id)
        )
        return result.scalar_one_or_none()
