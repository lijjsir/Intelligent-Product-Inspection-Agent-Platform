from __future__ import annotations

from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.services.base import TenantAwareService


class BillingService(TenantAwareService):
    def __init__(self, session, org_id: str):
        super().__init__(session, org_id)
        self._repo = TokenLedgerRepository(session)

    async def get_summary(self, query):
        items, buckets = await self._repo.aggregate(
            self._org_id,
            query.granularity,
            query.start_date,
            query.end_date,
            query.model_key,
            query.product_line,
        )
        total_tokens = sum(int(item.total_tokens or 0) for item in items)
        total_cost = round(sum(float(item.cost_amount or 0.0) for item in items), 4)
        return {
            "granularity": query.granularity,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "buckets": buckets,
            "ledger_items": items[:200],
        }

