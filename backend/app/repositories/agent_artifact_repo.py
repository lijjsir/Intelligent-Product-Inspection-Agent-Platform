from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_ops import AgentArtifactRecord


class AgentArtifactRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_once(self, payload: dict[str, Any]) -> AgentArtifactRecord | None:
        stmt = select(AgentArtifactRecord).where(
            AgentArtifactRecord.org_id == payload["org_id"],
            AgentArtifactRecord.request_id == payload["request_id"],
            AgentArtifactRecord.artifact_id == payload["artifact_id"],
        )
        existing = (await self._session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing
        row = AgentArtifactRecord(**payload)
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_request(self, *, org_id: str, request_id: str) -> list[AgentArtifactRecord]:
        stmt = (
            select(AgentArtifactRecord)
            .where(
                AgentArtifactRecord.org_id == org_id,
                AgentArtifactRecord.request_id == request_id,
                AgentArtifactRecord.deleted_at.is_(None),
            )
            .order_by(AgentArtifactRecord.created_at.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())
