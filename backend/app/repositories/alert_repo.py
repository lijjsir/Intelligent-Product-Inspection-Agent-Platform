from datetime import datetime, timezone

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertEvent
from app.models.stability import StabilityReport
from app.models.task import InspectionTask


class AlertRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, org_id: str | None, alert_id: str) -> AlertEvent | None:
        stmt = (
            select(AlertEvent)
            .outerjoin(StabilityReport, StabilityReport.id == AlertEvent.stability_id)
            .outerjoin(InspectionTask, InspectionTask.id == StabilityReport.task_id)
            .where(
                AlertEvent.id == alert_id,
                (StabilityReport.id.is_(None)) | (InspectionTask.deleted_at.is_(None)),
            )
        )
        if org_id:
            stmt = stmt.where(AlertEvent.org_id == org_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, payload: dict) -> AlertEvent:
        alert = AlertEvent(**payload)
        self._session.add(alert)
        await self._session.flush()
        return alert

    async def get_by_idempotency_key(self, idempotency_key: str) -> AlertEvent | None:
        result = await self._session.execute(
            select(AlertEvent).where(AlertEvent.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def create_once(self, payload: dict) -> AlertEvent:
        key = payload.get("idempotency_key")
        if key:
            existing = await self.get_by_idempotency_key(str(key))
            if existing is not None:
                return existing
        return await self.create(payload)

    async def list_alerts(
        self,
        org_id: str | None,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        severity: str | None = None
    ):
        query = (
            select(AlertEvent)
            .outerjoin(StabilityReport, StabilityReport.id == AlertEvent.stability_id)
            .outerjoin(InspectionTask, InspectionTask.id == StabilityReport.task_id)
            .where((StabilityReport.id.is_(None)) | (InspectionTask.deleted_at.is_(None)))
        )
        if org_id:
            query = query.where(AlertEvent.org_id == org_id)
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

    async def update_status(self, org_id: str | None, alert_id: str, status: str, resolved_by: str, resolved_at) -> bool:
        stmt = update(AlertEvent).where(AlertEvent.id == alert_id)
        if org_id:
            stmt = stmt.where(AlertEvent.org_id == org_id)
        stmt = stmt.values(status=status, resolved_by=resolved_by, resolved_at=resolved_at)
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def handle_alert(self, org_id: str | None, alert_id: str, values: dict) -> bool:
        stmt = update(AlertEvent).where(AlertEvent.id == alert_id)
        if org_id:
            stmt = stmt.where(AlertEvent.org_id == org_id)
        stmt = stmt.values(**values)
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def get_latest_by_rule(
        self, org_id: str | None, rule_id: str, since: datetime
    ) -> AlertEvent | None:
        """Return the most recent alert for this rule within the cooldown window."""
        stmt = (
            select(AlertEvent)
            .where(
                AlertEvent.rule_id == rule_id,
                AlertEvent.created_at >= since,
            )
        )
        if org_id:
            stmt = stmt.where(AlertEvent.org_id == org_id)
        stmt = stmt.order_by(AlertEvent.created_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_stability(self, org_id: str | None, stability_id: str) -> list[AlertEvent]:
        """Return all alerts linked to a stability report."""
        stmt = select(AlertEvent).where(AlertEvent.stability_id == stability_id)
        if org_id:
            stmt = stmt.where(AlertEvent.org_id == org_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(self, org_id: str | None, alert_id: str) -> None:
        """Soft-delete an alert event."""
        from datetime import datetime as dt
        stmt = (
            update(AlertEvent)
            .where(AlertEvent.id == alert_id)
            .values(deleted_at=dt.utcnow())
        )
        if org_id:
            stmt = stmt.where(AlertEvent.org_id == org_id)
        await self._session.execute(stmt)

    async def nullify_rule_id(self, org_id: str | None, rule_id: str) -> None:
        """Set rule_id to NULL on all alert_events referencing the given rule."""
        stmt = (
            update(AlertEvent)
            .where(AlertEvent.rule_id == rule_id)
            .values(rule_id=None)
        )
        if org_id:
            stmt = stmt.where(AlertEvent.org_id == org_id)
        await self._session.execute(stmt)
