from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.user import User
from app.models.user_token_usage import UserTokenUsageSummary


class UserTokenUsageSummaryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def increment(
        self,
        *,
        org_id: str,
        user_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_amount: float,
        ledger_created_at: datetime | None = None,
    ) -> None:
        ledger_created_at = ledger_created_at or utcnow()
        stmt = insert(UserTokenUsageSummary).values(
            user_id=user_id,
            org_id=org_id,
            total_prompt_tokens=prompt_tokens,
            total_completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            total_cost=cost_amount,
            request_count=1,
            last_ledger_at=ledger_created_at,
        )
        stmt = stmt.on_duplicate_key_update(
            org_id=stmt.inserted.org_id,
            total_prompt_tokens=UserTokenUsageSummary.total_prompt_tokens + stmt.inserted.total_prompt_tokens,
            total_completion_tokens=(
                UserTokenUsageSummary.total_completion_tokens + stmt.inserted.total_completion_tokens
            ),
            total_tokens=UserTokenUsageSummary.total_tokens + stmt.inserted.total_tokens,
            total_cost=UserTokenUsageSummary.total_cost + stmt.inserted.total_cost,
            request_count=UserTokenUsageSummary.request_count + 1,
            last_ledger_at=func.greatest(
                func.ifnull(UserTokenUsageSummary.last_ledger_at, stmt.inserted.last_ledger_at),
                stmt.inserted.last_ledger_at,
            ),
            updated_at=func.current_timestamp(3),
        )
        await self._session.execute(stmt)

    async def get_for_user(self, *, user_id: str, org_id: str | None = None) -> UserTokenUsageSummary | None:
        stmt = select(UserTokenUsageSummary).where(UserTokenUsageSummary.user_id == user_id)
        if org_id:
            stmt = stmt.where(UserTokenUsageSummary.org_id == org_id)
        result = await self._session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def list_with_users(self, *, org_id: str | None = None) -> list[dict]:
        stmt: Select = (
            select(
                UserTokenUsageSummary.user_id,
                UserTokenUsageSummary.org_id,
                User.username,
                User.role,
                UserTokenUsageSummary.total_prompt_tokens,
                UserTokenUsageSummary.total_completion_tokens,
                UserTokenUsageSummary.total_tokens,
                UserTokenUsageSummary.total_cost,
                UserTokenUsageSummary.request_count,
                UserTokenUsageSummary.last_ledger_at,
                UserTokenUsageSummary.updated_at,
            )
            .join(User, User.id == UserTokenUsageSummary.user_id)
            .order_by(UserTokenUsageSummary.total_tokens.desc(), User.username.asc())
        )
        if org_id:
            stmt = stmt.where(UserTokenUsageSummary.org_id == org_id)
        result = await self._session.execute(stmt)
        return [dict(row._mapping) for row in result]
