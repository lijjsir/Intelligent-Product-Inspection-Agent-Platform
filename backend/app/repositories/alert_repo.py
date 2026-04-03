from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertEvent


class AlertRepository:
    def __init__(self, session: AsyncSession):
        """封装告警事件的创建、筛选和状态更新。"""
        self._session = session

    async def get(self, org_id: str, alert_id: str) -> AlertEvent | None:
        """按租户和告警 ID 查询单条告警。"""
        result = await self._session.execute(
            select(AlertEvent).where(AlertEvent.org_id == org_id, AlertEvent.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def create(self, payload: dict) -> AlertEvent:
        """创建一条新的告警事件。"""
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
        """按状态和严重级别筛选告警，并返回总数和明细列表。"""
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
        """更新告警状态及其处理人、处理时间。"""
        stmt = (
            update(AlertEvent)
            .where(AlertEvent.org_id == org_id, AlertEvent.id == alert_id)
            .values(status=status, resolved_by=resolved_by, resolved_at=resolved_at)
        )
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def handle_alert(self, org_id: str, alert_id: str, values: dict) -> bool:
        """按传入字段批量更新告警处理结果。"""
        stmt = (
            update(AlertEvent)
            .where(AlertEvent.org_id == org_id, AlertEvent.id == alert_id)
            .values(**values)
        )
        res = await self._session.execute(stmt)
        return res.rowcount > 0
