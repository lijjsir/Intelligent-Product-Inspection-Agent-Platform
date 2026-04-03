from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stability import StabilityReport


class StabilityRepository:
    def __init__(self, session: AsyncSession):
        """封装稳定性报告的查询和按任务幂等写入操作。"""
        self._session = session

    async def get_by_task(self, org_id: str, task_id: str) -> StabilityReport | None:
        """按任务查询稳定性报告。"""
        result = await self._session.execute(
            select(StabilityReport).where(
                StabilityReport.org_id == org_id, StabilityReport.task_id == task_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert_by_task(self, payload: dict) -> StabilityReport:
        """按 task_id 幂等写入稳定性报告。"""
        existing = await self.get_by_task(payload["org_id"], payload["task_id"])
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
            await self._session.flush()
            return existing

        obj = StabilityReport(**payload)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def list_by_range(self, org_id: str, start_date=None, end_date=None) -> list[StabilityReport]:
        """按时间范围查询稳定性报告列表。"""
        stmt = select(StabilityReport).where(StabilityReport.org_id == org_id)
        if start_date:
            stmt = stmt.where(StabilityReport.created_at >= __import__("datetime").datetime.combine(start_date, __import__("datetime").datetime.min.time()))
        if end_date:
            stmt = stmt.where(StabilityReport.created_at <= __import__("datetime").datetime.combine(end_date, __import__("datetime").datetime.max.time()))
        result = await self._session.execute(stmt.order_by(StabilityReport.created_at.asc()))
        return list(result.scalars().all())
