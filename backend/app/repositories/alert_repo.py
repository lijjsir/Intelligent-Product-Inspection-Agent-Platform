from sqlalchemy import select, func, update
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

    async def create(self, payload: dict) -> AlertEvent:
        alert = AlertEvent(**payload)
        self._session.add(alert)
        await self._session.flush()
        return alert

    async def list_alerts(
        self,
        org_id: str,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        severity: str | None = None
    ):
        query = select(AlertEvent).where(AlertEvent.org_id == org_id)
        if status:
            query = query.where(AlertEvent.status == status)
        if severity:
            query = query.where(AlertEvent.severity == severity)
            
        total_stmt = select(func.count()).select_from(query.subquery())
        total_res = await self._session.execute(total_stmt)
        total = total_res.scalar_one()

        query = query.order_by(AlertEvent.created_at.desc()).offset(skip).limit(limit)
        items_res = await self._session.execute(query)
        items = items_res.scalars().all()
        return total, list(items)

    async def update_status(self, org_id: str, alert_id: str, status: str, resolved_by: str, resolved_at) -> bool:
        stmt = (
            update(AlertEvent)
            .where(AlertEvent.org_id == org_id, AlertEvent.id == alert_id)
            .values(status=status, resolved_by=resolved_by, resolved_at=resolved_at)
        )
        res = await self._session.execute(stmt)
        return res.rowcount > 0
