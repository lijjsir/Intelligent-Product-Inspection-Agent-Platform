from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.agent_management import AgentExecutionMetrics, AgentConfigVersion
from app.models.agent_ops import AgentDefinition


class AgentExecutionMetricsRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def get_or_create(self, agent_id: str) -> AgentExecutionMetrics:
        result = await self._session.execute(
            select(AgentExecutionMetrics).where(
                AgentExecutionMetrics.org_id == self._org_id,
                AgentExecutionMetrics.agent_id == agent_id,
            )
        )
        metrics = result.scalar_one_or_none()
        if not metrics:
            metrics = AgentExecutionMetrics(org_id=self._org_id, agent_id=agent_id)
            self._session.add(metrics)
            await self._session.flush()
        return metrics

    async def update_metrics(self, agent_id: str, success: bool, latency_ms: int) -> None:
        metrics = await self.get_or_create(agent_id)
        metrics.execution_count += 1
        if success:
            metrics.success_count += 1
        metrics.total_latency_ms += latency_ms
        metrics.last_executed_at = utcnow()
        await self._session.flush()

    async def get_metrics(self, agent_id: str) -> dict | None:
        result = await self._session.execute(
            select(AgentExecutionMetrics).where(
                AgentExecutionMetrics.org_id == self._org_id,
                AgentExecutionMetrics.agent_id == agent_id,
            )
        )
        metrics = result.scalar_one_or_none()
        if not metrics:
            return None
        avg_latency = metrics.total_latency_ms / metrics.execution_count if metrics.execution_count > 0 else 0.0
        success_rate = metrics.success_count / metrics.execution_count if metrics.execution_count > 0 else 0.0
        return {
            "execution_count": metrics.execution_count,
            "success_count": metrics.success_count,
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency,
            "last_executed_at": metrics.last_executed_at,
        }


class AgentConfigVersionRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def create_version(self, agent_id: str, config: dict, created_by: str | None = None) -> AgentConfigVersion:
        max_version_result = await self._session.execute(
            select(func.coalesce(func.max(AgentConfigVersion.version), 0)).where(
                AgentConfigVersion.org_id == self._org_id,
                AgentConfigVersion.agent_id == agent_id,
            )
        )
        max_version = max_version_result.scalar() or 0
        version = AgentConfigVersion(
            org_id=self._org_id,
            agent_id=agent_id,
            version=max_version + 1,
            config_snapshot=config,
            created_by=created_by,
            is_active=True,
        )
        self._session.add(version)
        await self._session.flush()
        return version

    async def get_version(self, agent_id: str, version: int) -> AgentConfigVersion | None:
        result = await self._session.execute(
            select(AgentConfigVersion).where(
                AgentConfigVersion.org_id == self._org_id,
                AgentConfigVersion.agent_id == agent_id,
                AgentConfigVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def list_versions(self, agent_id: str, limit: int = 10) -> list[AgentConfigVersion]:
        result = await self._session.execute(
            select(AgentConfigVersion).where(
                AgentConfigVersion.org_id == self._org_id,
                AgentConfigVersion.agent_id == agent_id,
            ).order_by(AgentConfigVersion.version.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest_version(self, agent_id: str) -> AgentConfigVersion | None:
        result = await self._session.execute(
            select(AgentConfigVersion).where(
                AgentConfigVersion.org_id == self._org_id,
                AgentConfigVersion.agent_id == agent_id,
            ).order_by(AgentConfigVersion.version.desc()).limit(1)
        )
        return result.scalar_one_or_none()


class AgentBatchOperationRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def batch_update_status(self, agent_ids: list[str], is_active: bool) -> int:
        stmt = update(AgentDefinition).where(
            AgentDefinition.org_id == self._org_id,
            AgentDefinition.id.in_(agent_ids),
            AgentDefinition.deleted_at.is_(None),
        ).values(is_active=is_active)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def batch_delete(self, agent_ids: list[str]) -> int:
        stmt = update(AgentDefinition).where(
            AgentDefinition.org_id == self._org_id,
            AgentDefinition.id.in_(agent_ids),
            AgentDefinition.deleted_at.is_(None),
        ).values(deleted_at=utcnow())
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount
