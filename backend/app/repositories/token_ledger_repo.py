from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_ledger import TokenUsageLedger


class TokenLedgerRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_by_trace_id(self, trace_id: str) -> list[TokenUsageLedger]:
        stmt = select(TokenUsageLedger).where(TokenUsageLedger.trace_id == trace_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, payload: dict) -> TokenUsageLedger:
        obj = TokenUsageLedger(**payload)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def list_filtered(
        self,
        org_id: str | None,
        start_date: date | None = None,
        end_date: date | None = None,
        model_key: str | None = None,
        product_line: str | None = None,
    ) -> list[TokenUsageLedger]:
        stmt = select(TokenUsageLedger)
        if org_id:
            stmt = stmt.where(TokenUsageLedger.org_id == org_id)
        if start_date:
            stmt = stmt.where(TokenUsageLedger.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            stmt = stmt.where(TokenUsageLedger.created_at <= datetime.combine(end_date, datetime.max.time()))
        if model_key:
            stmt = stmt.where(TokenUsageLedger.model_key == model_key)
        if product_line:
            stmt = stmt.where(TokenUsageLedger.product_line == product_line)
        stmt = stmt.order_by(TokenUsageLedger.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def aggregate(
        self,
        org_id: str | None,
        granularity: str,
        start_date: date | None = None,
        end_date: date | None = None,
        model_key: str | None = None,
        product_line: str | None = None,
    ) -> tuple[list[TokenUsageLedger], list[dict]]:
        items = await self.list_filtered(org_id, start_date, end_date, model_key, product_line)
        buckets: dict[str, dict] = defaultdict(lambda: {"total_tokens": 0, "total_cost": 0.0, "request_count": 0})
        for item in items:
            key = self._bucket_key(item.created_at, granularity)
            bucket = buckets[key]
            bucket["total_tokens"] += int(item.total_tokens or 0)
            bucket["total_cost"] += float(item.cost_amount or 0.0)
            bucket["request_count"] += 1
        summary = [
            {
                "bucket": key,
                "total_tokens": value["total_tokens"],
                "total_cost": round(value["total_cost"], 4),
                "request_count": value["request_count"],
            }
            for key, value in sorted(buckets.items())
        ]
        return items, summary

    @staticmethod
    def _bucket_key(created_at: datetime, granularity: str) -> str:
        if granularity == "week":
            year, week, _ = created_at.isocalendar()
            return f"{year}-W{week:02d}"
        if granularity == "month":
            return created_at.strftime("%Y-%m")
        return created_at.strftime("%Y-%m-%d")

