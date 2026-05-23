from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from datetime import datetime

from app.models.audit import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def write(self, audit: AuditLog) -> AuditLog:
        self._session.add(audit)
        await self._session.flush()
        return audit

    def _apply_filters(
        self,
        stmt,
        org_id: str,
        actor_id: str | None = None,
        resource_type: str | None = None,
        action: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        stmt = stmt.where(AuditLog.org_id == org_id)
        if actor_id:
            stmt = stmt.where(AuditLog.actor_id == actor_id)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if start_date:
            stmt = stmt.where(AuditLog.occurred_at >= start_date)
        if end_date:
            stmt = stmt.where(AuditLog.occurred_at <= end_date)
        return stmt

    async def list_logs(
        self,
        org_id: str,
        page: int,
        size: int,
        actor_id: str | None = None,
        resource_type: str | None = None,
        action: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> tuple[list[AuditLog], int]:
        offset = (page - 1) * size
        stmt = self._apply_filters(
            select(AuditLog),
            org_id=org_id,
            actor_id=actor_id,
            resource_type=resource_type,
            action=action,
            start_date=start_date,
            end_date=end_date,
        )
        result = await self._session.execute(
            stmt.order_by(AuditLog.occurred_at.desc()).offset(offset).limit(size)
        )
        items = list(result.scalars().all())
        count_stmt = self._apply_filters(
            select(func.count()).select_from(AuditLog),
            org_id=org_id,
            actor_id=actor_id,
            resource_type=resource_type,
            action=action,
            start_date=start_date,
            end_date=end_date,
        )
        count_result = await self._session.execute(count_stmt)
        return items, int(count_result.scalar() or 0)
