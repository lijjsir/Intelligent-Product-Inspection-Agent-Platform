from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.repositories.tool_repo import ToolRepository


class ToolHealthService:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id
        self._repo = ToolRepository(session)

    async def check_health(self) -> list[dict]:
        tools = await self._repo.list_all(self._org_id)
        results = []
        for tool in tools:
            recent = await self._repo.list_recent_executions(
                self._org_id,
                tool_id=tool.id,
                since=utcnow() - timedelta(hours=1),
                limit=20,
            )
            successes = sum(1 for r in recent if r.status == "success")
            total = len(recent)
            health = "unknown"
            if total > 0:
                rate = successes / total
                health = "healthy" if rate >= 0.95 else "degraded" if rate >= 0.7 else "unhealthy"
            results.append({
                "tool_id": tool.id,
                "tool_key": tool.tool_key,
                "health": health,
                "success_rate": round(successes / total, 4) if total else None,
                "recent_calls": total,
            })
        return results
