from collections import Counter
from datetime import date, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import ResultFeedback


class FeedbackRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_actor_feedback(self, result_id: str, actor_id: str) -> ResultFeedback | None:
        result = await self._session.execute(
            select(ResultFeedback).where(
                ResultFeedback.result_id == result_id,
                ResultFeedback.actor_id == actor_id,
            )
        )
        return result.scalar_one_or_none()

    async def save(self, payload: dict) -> ResultFeedback:
        existing = await self.get_actor_feedback(payload["result_id"], payload["actor_id"])
        if existing:
            for key, value in payload.items():
                if key != "id":
                    setattr(existing, key, value)
            await self._session.flush()
            return existing
        obj = ResultFeedback(**payload)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def list_feedbacks(
        self,
        org_id: str,
        page: int,
        size: int,
        result_id: str | None = None,
        feedback_type: str | None = None,
    ) -> tuple[int, list[ResultFeedback]]:
        stmt = select(ResultFeedback).where(ResultFeedback.org_id == org_id)
        if result_id:
            stmt = stmt.where(ResultFeedback.result_id == result_id)
        if feedback_type:
            stmt = stmt.where(ResultFeedback.feedback_type == feedback_type)
        result = await self._session.execute(stmt.order_by(ResultFeedback.created_at.desc()))
        items = list(result.scalars().all())
        total = len(items)
        start = (page - 1) * size
        return total, items[start : start + size]

    async def list_by_range(self, org_id: str, start_date: date | None = None, end_date: date | None = None) -> list[ResultFeedback]:
        stmt = select(ResultFeedback).where(ResultFeedback.org_id == org_id)
        if start_date:
            stmt = stmt.where(ResultFeedback.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            stmt = stmt.where(ResultFeedback.created_at <= datetime.combine(end_date, datetime.max.time()))
        result = await self._session.execute(stmt.order_by(ResultFeedback.created_at.asc()))
        return list(result.scalars().all())

    async def category_distribution(self, org_id: str, start_date: date | None = None, end_date: date | None = None) -> dict[str, int]:
        items = await self.list_by_range(org_id, start_date, end_date)
        counter = Counter((item.category or "uncategorized") for item in items)
        return dict(counter)

