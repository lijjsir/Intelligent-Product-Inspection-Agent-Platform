from collections import Counter
from datetime import date, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import MessageFeedback, ResultFeedback


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

    async def get_by_id(self, feedback_id: str) -> ResultFeedback | None:
        result = await self._session.execute(
            select(ResultFeedback).where(ResultFeedback.id == feedback_id)
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

    async def get_actor_message_feedback(
        self,
        *,
        target_type: str,
        target_id: str,
        actor_id: str,
    ) -> MessageFeedback | None:
        result = await self._session.execute(
            select(MessageFeedback).where(
                MessageFeedback.target_type == target_type,
                MessageFeedback.target_id == target_id,
                MessageFeedback.actor_id == actor_id,
            )
        )
        return result.scalar_one_or_none()

    async def save_message_feedback(self, payload: dict) -> MessageFeedback:
        existing = await self.get_actor_message_feedback(
            target_type=payload["target_type"],
            target_id=payload["target_id"],
            actor_id=payload["actor_id"],
        )
        if existing:
            for key, value in payload.items():
                if key != "id":
                    setattr(existing, key, value)
            await self._session.flush()
            return existing
        obj = MessageFeedback(**payload)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def list_message_feedbacks(
        self,
        *,
        org_id: str,
        target_type: str,
        actor_id: str,
        target_ids: list[str] | None = None,
    ) -> list[MessageFeedback]:
        stmt = select(MessageFeedback).where(
            MessageFeedback.org_id == org_id,
            MessageFeedback.target_type == target_type,
            MessageFeedback.actor_id == actor_id,
        )
        if target_ids:
            stmt = stmt.where(MessageFeedback.target_id.in_(target_ids))
        result = await self._session.execute(stmt.order_by(MessageFeedback.updated_at.desc()))
        return list(result.scalars().all())

    async def list_feedbacks(
        self,
        org_id: str,
        page: int,
        size: int,
        result_id: str | None = None,
        feedback_type: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        source_type: str | None = None,
        category: str | None = None,
        assigned_to: str | None = None,
    ) -> tuple[int, list[ResultFeedback]]:
        stmt = select(ResultFeedback).where(ResultFeedback.org_id == org_id)
        if result_id:
            stmt = stmt.where(ResultFeedback.result_id == result_id)
        if feedback_type:
            stmt = stmt.where(ResultFeedback.feedback_type == feedback_type)
        if status:
            stmt = stmt.where(ResultFeedback.status == status)
        if severity:
            stmt = stmt.where(ResultFeedback.severity == severity)
        if source_type:
            stmt = stmt.where(ResultFeedback.source_type == source_type)
        if category:
            stmt = stmt.where(ResultFeedback.category == category)
        if assigned_to:
            stmt = stmt.where(ResultFeedback.assigned_to == assigned_to)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(ResultFeedback.created_at.desc()).offset((page - 1) * size).limit(size)
        result = await self._session.execute(stmt)
        return total, list(result.scalars().all())

    async def list_by_range(self, org_id: str | None, start_date: date | None = None, end_date: date | None = None) -> list[ResultFeedback]:
        stmt = select(ResultFeedback)
        if org_id:
            stmt = stmt.where(ResultFeedback.org_id == org_id)
        if start_date:
            stmt = stmt.where(ResultFeedback.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            stmt = stmt.where(ResultFeedback.created_at <= datetime.combine(end_date, datetime.max.time()))
        result = await self._session.execute(stmt.order_by(ResultFeedback.created_at.asc()))
        return list(result.scalars().all())

    async def list_message_by_range(
        self,
        org_id: str | None,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        target_type: str | None = None,
    ) -> list[MessageFeedback]:
        stmt = select(MessageFeedback)
        if org_id:
            stmt = stmt.where(MessageFeedback.org_id == org_id)
        if target_type:
            stmt = stmt.where(MessageFeedback.target_type == target_type)
        if start_date:
            stmt = stmt.where(MessageFeedback.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            stmt = stmt.where(MessageFeedback.created_at <= datetime.combine(end_date, datetime.max.time()))
        result = await self._session.execute(stmt.order_by(MessageFeedback.created_at.asc()))
        return list(result.scalars().all())

    async def category_distribution(self, org_id: str, start_date: date | None = None, end_date: date | None = None) -> dict[str, int]:
        items = await self.list_by_range(org_id, start_date, end_date)
        counter = Counter((item.category or "uncategorized") for item in items)
        return dict(counter)

    async def summary(self, org_id: str) -> dict:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        base = select(ResultFeedback).where(ResultFeedback.org_id == org_id)
        today_new = (await self._session.execute(
            select(func.count()).select_from(
                base.where(ResultFeedback.created_at >= today_start).subquery()
            )
        )).scalar() or 0
        pending_count = (await self._session.execute(
            select(func.count()).select_from(
                base.where(ResultFeedback.status == "pending").subquery()
            )
        )).scalar() or 0
        high_risk_count = (await self._session.execute(
            select(func.count()).select_from(
                base.where(ResultFeedback.severity.in_(["high", "critical"])).subquery()
            )
        )).scalar() or 0
        total = (await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar() or 0
        resolved = (await self._session.execute(
            select(func.count()).select_from(
                base.where(ResultFeedback.status == "resolved").subquery()
            )
        )).scalar() or 0
        resolved_rate = round(resolved / total, 4) if total > 0 else 0.0
        avg_hours_result = (await self._session.execute(
            select(func.avg(func.timestampdiff(text("HOUR"), ResultFeedback.created_at, ResultFeedback.resolved_at)))
            .where(ResultFeedback.org_id == org_id, ResultFeedback.resolved_at.isnot(None))
        )).scalar()
        avg_resolution_hours = round(float(avg_hours_result), 1) if avg_hours_result else None
        return {
            "today_new": today_new,
            "pending_count": pending_count,
            "high_risk_count": high_risk_count,
            "resolved_rate": resolved_rate,
            "avg_resolution_hours": avg_resolution_hours,
        }
