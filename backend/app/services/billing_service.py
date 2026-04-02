from __future__ import annotations

from app.repositories.token_ledger_repo import TokenLedgerRepository
from app.repositories.user_token_usage_repo import UserTokenUsageSummaryRepository
from app.services.base import TenantAwareService


class BillingService(TenantAwareService):
    def __init__(self, session, org_id: str, actor_role: str = "user"):
        super().__init__(session, org_id)
        self._repo = TokenLedgerRepository(session)
        self._user_summary_repo = UserTokenUsageSummaryRepository(session)
        self._scope_org_id = None if actor_role == "admin" else org_id

    async def get_summary(self, query):
        items, buckets = await self._repo.aggregate(
            self._scope_org_id,
            query.granularity,
            query.start_date,
            query.end_date,
            query.model_key,
            query.product_line,
        )
        user_summaries = await self._user_summary_repo.list_with_users(org_id=self._scope_org_id)
        total_tokens = sum(int(item.total_tokens or 0) for item in items)
        total_cost = round(sum(float(item.cost_amount or 0.0) for item in items), 4)
        return {
            "granularity": query.granularity,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "buckets": buckets,
            "ledger_items": items[:200],
            "user_summaries": user_summaries,
        }

    async def get_current_user_summary(self, *, user_id: str) -> dict:
        row = await self._user_summary_repo.get_for_user(user_id=user_id, org_id=self._org_id)
        if not row:
            return {
                "user_id": user_id,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "request_count": 0,
                "last_ledger_at": None,
            }
        return {
            "user_id": row.user_id,
            "total_prompt_tokens": int(row.total_prompt_tokens or 0),
            "total_completion_tokens": int(row.total_completion_tokens or 0),
            "total_tokens": int(row.total_tokens or 0),
            "total_cost": round(float(row.total_cost or 0.0), 4),
            "request_count": int(row.request_count or 0),
            "last_ledger_at": row.last_ledger_at,
        }

