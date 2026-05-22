from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.chat import ChatMessageScore


class ChatMessageScoreRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_by_message_version(self, payload: dict) -> ChatMessageScore:
        existing = await self.get_by_message_version(
            org_id=str(payload["org_id"]),
            assistant_message_id=str(payload["assistant_message_id"]),
            score_version=str(payload.get("score_version") or "trust_v1"),
        )
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            await self._session.flush()
            await self._session.refresh(existing, attribute_names=["updated_at"])
            return existing

        obj = ChatMessageScore(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get_by_message_version(
        self,
        *,
        org_id: str,
        assistant_message_id: str,
        score_version: str = "trust_v1",
    ) -> ChatMessageScore | None:
        result = await self._session.execute(
            select(ChatMessageScore).where(
                ChatMessageScore.org_id == org_id,
                ChatMessageScore.assistant_message_id == assistant_message_id,
                ChatMessageScore.score_version == score_version,
                ChatMessageScore.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def find_by_trace_id(self, trace_id: str) -> list[ChatMessageScore]:
        result = await self._session.execute(
            select(ChatMessageScore).where(
                ChatMessageScore.trace_id == trace_id,
                ChatMessageScore.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def soft_delete(self, score_id: str) -> None:
        from datetime import datetime as dt
        obj = await self._session.get(ChatMessageScore, score_id)
        if obj:
            obj.deleted_at = utcnow()
            await self._session.flush()

    async def list_by_range(
        self,
        org_id: str | None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
    ) -> list[ChatMessageScore]:
        stmt = select(ChatMessageScore).where(ChatMessageScore.deleted_at.is_(None))
        if org_id:
            stmt = stmt.where(ChatMessageScore.org_id == org_id)
        if start_date:
            stmt = stmt.where(ChatMessageScore.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            stmt = stmt.where(ChatMessageScore.created_at <= datetime.combine(end_date, datetime.max.time()))
        stmt = stmt.order_by(ChatMessageScore.created_at.desc())
        if limit:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
