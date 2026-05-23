from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_log import AuthLog


class AuthLogRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def write(self, log: AuthLog) -> AuthLog:
        self._session.add(log)
        await self._session.flush()
        return log

    def _apply_filters(
        self,
        stmt,
        org_id: str,
        user_id: str | None = None,
        event_type: str | None = None,
        ip_address: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        stmt = stmt.where(AuthLog.org_id == org_id)
        if user_id:
            stmt = stmt.where(AuthLog.user_id == user_id)
        if event_type:
            stmt = stmt.where(AuthLog.event_type == event_type)
        if ip_address:
            stmt = stmt.where(AuthLog.ip_address == ip_address)
        if start_date:
            stmt = stmt.where(AuthLog.occurred_at >= start_date)
        if end_date:
            stmt = stmt.where(AuthLog.occurred_at <= end_date)
        return stmt

    async def list_logs(
        self,
        org_id: str,
        page: int,
        size: int,
        user_id: str | None = None,
        event_type: str | None = None,
        ip_address: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> tuple[list[AuthLog], int]:
        offset = (page - 1) * size
        stmt = self._apply_filters(
            select(AuthLog),
            org_id,
            user_id=user_id,
            event_type=event_type,
            ip_address=ip_address,
            start_date=start_date,
            end_date=end_date,
        )
        result = await self._session.execute(
            stmt.order_by(AuthLog.occurred_at.desc()).offset(offset).limit(size)
        )
        items = list(result.scalars().all())

        count_stmt = self._apply_filters(
            select(func.count()).select_from(AuthLog),
            org_id,
            user_id=user_id,
            event_type=event_type,
            ip_address=ip_address,
            start_date=start_date,
            end_date=end_date,
        )
        count_result = await self._session.execute(count_stmt)
        total = int(count_result.scalar() or 0)
        return items, total
