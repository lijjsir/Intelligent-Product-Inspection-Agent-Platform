from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypeVar

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime import utcnow
from app.models.agent_ops import (
    AgentDefinition,
    AgentRouteLog,
    AgentRuntimeInstance,
    IntentRoute,
    PromptVersion,
    RagQueryLog,
)

T = TypeVar("T")


class AgentOpsRepository:
    def __init__(self, session: AsyncSession, org_id: str | None):
        self._session = session
        self._org_id = org_id

    async def _get_by_id(self, model: type[T], id: str) -> T | None:
        filters = [model.id == id, model.deleted_at.is_(None)]
        if self._org_id is not None:
            filters.insert(0, model.org_id == self._org_id)
        result = await self._session.execute(select(model).where(*filters))
        return result.scalar_one_or_none()


class AgentDefinitionRepository(AgentOpsRepository):
    async def create(self, data: dict) -> AgentDefinition:
        obj = AgentDefinition(**data, org_id=self._org_id)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, id: str) -> AgentDefinition | None:
        return await self._get_by_id(AgentDefinition, id)

    async def get_by_subgraph_key(self, subgraph_key: str) -> AgentDefinition | None:
        items = await self.list_by_subgraph_key(subgraph_key)
        return items[0] if items else None

    async def list_by_subgraph_key(self, subgraph_key: str) -> list[AgentDefinition]:
        result = await self._session.execute(
            select(AgentDefinition).where(
                AgentDefinition.org_id == self._org_id,
                AgentDefinition.subgraph_key == subgraph_key,
                AgentDefinition.deleted_at.is_(None),
            )
            .order_by(
                AgentDefinition.updated_at.desc(),
                AgentDefinition.created_at.desc(),
                AgentDefinition.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def dedupe_by_subgraph_key(self, subgraph_key: str) -> AgentDefinition | None:
        items = await self.list_by_subgraph_key(subgraph_key)
        if not items:
            return None
        canonical = items[0]
        if len(items) == 1:
            return canonical
        now = utcnow()
        for duplicate in items[1:]:
            duplicate.is_active = False
            duplicate.deleted_at = now
        await self._session.flush()
        return canonical

    async def update(self, id: str, data: dict) -> AgentDefinition | None:
        obj = await self.get(id)
        if not obj:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["updated_at"])
        return obj

    async def delete(self, id: str) -> bool:
        obj = await self.get(id)
        if not obj:
            return False
        from datetime import datetime
        obj.deleted_at = utcnow()
        await self._session.flush()
        return True

    async def list_paged(self, filters: dict, page: int, size: int) -> tuple[list[AgentDefinition], int]:
        base = select(AgentDefinition).where(
            AgentDefinition.org_id == self._org_id, AgentDefinition.deleted_at.is_(None)
        )
        if "name" in filters:
            base = base.where(AgentDefinition.name.like(f"%{filters['name']}%"))
        if "is_active" in filters:
            base = base.where(AgentDefinition.is_active == filters["is_active"])

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        items = await self._session.execute(
            base.order_by(AgentDefinition.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        return list(items.scalars().all()), int(total or 0)

    async def list_all_active(self) -> list[AgentDefinition]:
        result = await self._session.execute(
            select(AgentDefinition).where(
                AgentDefinition.org_id == self._org_id,
                AgentDefinition.is_active == True,
                AgentDefinition.deleted_at.is_(None),
            ).order_by(AgentDefinition.name)
        )
        return list(result.scalars().all())


class PromptVersionRepository(AgentOpsRepository):
    async def create(self, data: dict) -> PromptVersion:
        obj = PromptVersion(**data, org_id=self._org_id)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, id: str) -> PromptVersion | None:
        return await self._get_by_id(PromptVersion, id)

    async def update(self, id: str, data: dict) -> PromptVersion | None:
        obj = await self.get(id)
        if not obj:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["updated_at"])
        return obj

    async def delete(self, id: str) -> bool:
        obj = await self.get(id)
        if not obj:
            return False
        from datetime import datetime
        obj.deleted_at = utcnow()
        await self._session.flush()
        return True

    async def list_paged(self, filters: dict, page: int, size: int) -> tuple[list[PromptVersion], int]:
        base = select(PromptVersion).where(
            PromptVersion.org_id == self._org_id, PromptVersion.deleted_at.is_(None)
        )
        if "name" in filters:
            base = base.where(PromptVersion.name.like(f"%{filters['name']}%"))
        if "status" in filters:
            base = base.where(PromptVersion.status == filters["status"])

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        items = await self._session.execute(
            base.order_by(PromptVersion.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        return list(items.scalars().all()), int(total or 0)

    async def get_latest_version(self, name: str) -> PromptVersion | None:
        result = await self._session.execute(
            select(PromptVersion)
            .where(
                PromptVersion.org_id == self._org_id,
                PromptVersion.name == name,
                PromptVersion.deleted_at.is_(None),
            )
            .order_by(PromptVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

class IntentRouteRepository(AgentOpsRepository):
    async def create(self, data: dict) -> IntentRoute:
        obj = IntentRoute(**data, org_id=self._org_id)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def get(self, id: str) -> IntentRoute | None:
        return await self._get_by_id(IntentRoute, id)

    async def update(self, id: str, data: dict) -> IntentRoute | None:
        obj = await self.get(id)
        if not obj:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["updated_at"])
        return obj

    async def delete(self, id: str) -> bool:
        obj = await self.get(id)
        if not obj:
            return False
        from datetime import datetime
        obj.deleted_at = utcnow()
        await self._session.flush()
        return True

    async def list_paged(self, filters: dict, page: int, size: int) -> tuple[list[IntentRoute], int]:
        base = select(IntentRoute).where(
            IntentRoute.org_id == self._org_id, IntentRoute.deleted_at.is_(None)
        )
        if "intent_name" in filters:
            base = base.where(IntentRoute.intent_name.like(f"%{filters['intent_name']}%"))
        if "is_active" in filters:
            base = base.where(IntentRoute.is_active == filters["is_active"])

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        items = await self._session.execute(
            base.order_by(IntentRoute.priority.desc(), IntentRoute.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(items.scalars().all()), int(total or 0)

    async def list_all_active(self) -> list[IntentRoute]:
        result = await self._session.execute(
            select(IntentRoute)
            .where(
                IntentRoute.org_id == self._org_id,
                IntentRoute.is_active == True,
                IntentRoute.deleted_at.is_(None),
            )
            .order_by(IntentRoute.priority.desc())
        )
        return list(result.scalars().all())


class RagAnalysisRepository(AgentOpsRepository):
    async def get_rag_stats(self, days: int = 90) -> dict:
        cutoff_date = utcnow() - timedelta(days=days)

        filters = [
            RagQueryLog.created_at >= cutoff_date,
            RagQueryLog.deleted_at.is_(None),
        ]
        if self._org_id is not None:
            filters.insert(0, RagQueryLog.org_id == self._org_id)

        stmt = select(
            func.count().label("total_queries"),
            func.coalesce(func.avg(RagQueryLog.hit_rate), 0.0).label("avg_hit_rate"),
            func.coalesce(func.avg(RagQueryLog.citation_coverage), 0.0).label("citation_coverage"),
            func.sum(case((RagQueryLog.hit_count == 0, 1), else_=0)).label("empty_recall_count"),
            func.coalesce(func.avg(RagQueryLog.latency_ms), 0.0).label("avg_latency_ms"),
        ).where(*filters)

        result = (await self._session.execute(stmt)).one()
        return {
            "total_queries": int(result.total_queries or 0),
            "avg_hit_rate": float(result.avg_hit_rate or 0.0),
            "citation_coverage": float(result.citation_coverage or 0.0),
            "empty_recall_count": int(result.empty_recall_count or 0),
            "avg_latency_ms": float(result.avg_latency_ms or 0.0),
        }

    async def get_recent_rag_items(self, limit: int = 10) -> list[dict]:
        filters = [RagQueryLog.deleted_at.is_(None)]
        if self._org_id is not None:
            filters.insert(0, RagQueryLog.org_id == self._org_id)

        stmt = select(
            RagQueryLog.task_id,
            RagQueryLog.session_id,
            RagQueryLog.query,
            RagQueryLog.rag_space_id,
            RagQueryLog.top_k,
            RagQueryLog.hit_count,
            RagQueryLog.hit_rate,
            RagQueryLog.citation_coverage,
            RagQueryLog.latency_ms,
            RagQueryLog.source_graph,
            RagQueryLog.agent_name,
            RagQueryLog.sub_route,
            RagQueryLog.trace_id,
            RagQueryLog.top_score,
            RagQueryLog.metadata_json,
            RagQueryLog.created_at,
        ).where(*filters).order_by(
            RagQueryLog.created_at.desc()
        ).limit(limit)

        results = (await self._session.execute(stmt)).all()
        items = []
        for row in results:
            items.append({
                "task_id": str(row.task_id or ""),
                "session_id": str(row.session_id or "") or None,
                "query": str(row.query or ""),
                "rag_space_id": str(row.rag_space_id or "") or None,
                "top_k": int(row.top_k or 0),
                "hit_count": int(row.hit_count or 0),
                "hit_rate": float(row.hit_rate or 0.0),
                "citation_coverage": float(row.citation_coverage or 0.0),
                "latency_ms": row.latency_ms or 0,
                "source_graph": str(row.source_graph or ""),
                "agent_name": str(row.agent_name or ""),
                "sub_route": str(row.sub_route or ""),
                "trace_id": str(row.trace_id or "") or None,
                "top_score": float(row.top_score or 0.0),
                "metadata": dict(row.metadata_json or {}),
                "created_at": row.created_at,
            })
        return items

    async def get_trace_detail(self, trace_id: str) -> dict | None:
        filters = [
            RagQueryLog.trace_id == trace_id,
            RagQueryLog.deleted_at.is_(None),
        ]
        if self._org_id is not None:
            filters.insert(0, RagQueryLog.org_id == self._org_id)

        stmt = (
            select(
                RagQueryLog.task_id,
                RagQueryLog.session_id,
                RagQueryLog.query,
                RagQueryLog.rag_space_id,
                RagQueryLog.top_k,
                RagQueryLog.hit_count,
                RagQueryLog.hit_rate,
                RagQueryLog.citation_coverage,
                RagQueryLog.latency_ms,
                RagQueryLog.source_graph,
                RagQueryLog.agent_name,
                RagQueryLog.sub_route,
                RagQueryLog.trace_id,
                RagQueryLog.top_score,
                RagQueryLog.metadata_json,
                RagQueryLog.created_at,
            )
            .where(*filters)
            .order_by(RagQueryLog.created_at.desc(), RagQueryLog.id.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return {
            "task_id": str(row.task_id or ""),
            "session_id": str(row.session_id or "") or None,
            "query": str(row.query or ""),
            "rag_space_id": str(row.rag_space_id or "") or None,
            "top_k": int(row.top_k or 0),
            "hit_count": int(row.hit_count or 0),
            "hit_rate": float(row.hit_rate or 0.0),
            "citation_coverage": float(row.citation_coverage or 0.0),
            "latency_ms": int(row.latency_ms or 0),
            "source_graph": str(row.source_graph or ""),
            "agent_name": str(row.agent_name or ""),
            "sub_route": str(row.sub_route or ""),
            "trace_id": str(row.trace_id or "") or None,
            "top_score": float(row.top_score or 0.0) if row.top_score is not None else None,
            "metadata": dict(row.metadata_json or {}),
            "created_at": row.created_at,
        }

    async def create_log(self, data: dict) -> RagQueryLog:
        obj = RagQueryLog(org_id=self._org_id, **data)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj


class AgentRuntimeRepository(AgentOpsRepository):
    async def get_by_agent_id(self, agent_id: str) -> AgentRuntimeInstance | None:
        items = await self.list_by_agent_id(agent_id)
        return items[0] if items else None

    async def list_by_agent_id(self, agent_id: str) -> list[AgentRuntimeInstance]:
        result = await self._session.execute(
            select(AgentRuntimeInstance).where(
                AgentRuntimeInstance.org_id == self._org_id,
                AgentRuntimeInstance.agent_id == agent_id,
                AgentRuntimeInstance.deleted_at.is_(None),
            )
            .order_by(
                AgentRuntimeInstance.updated_at.desc(),
                AgentRuntimeInstance.created_at.desc(),
                AgentRuntimeInstance.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_by_runtime_key(self, runtime_key: str) -> AgentRuntimeInstance | None:
        items = await self.list_by_runtime_key(runtime_key)
        return items[0] if items else None

    async def list_by_runtime_key(self, runtime_key: str) -> list[AgentRuntimeInstance]:
        result = await self._session.execute(
            select(AgentRuntimeInstance).where(
                AgentRuntimeInstance.org_id == self._org_id,
                AgentRuntimeInstance.runtime_key == runtime_key,
                AgentRuntimeInstance.deleted_at.is_(None),
            )
            .order_by(
                AgentRuntimeInstance.updated_at.desc(),
                AgentRuntimeInstance.created_at.desc(),
                AgentRuntimeInstance.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def dedupe_by_agent_id(self, agent_id: str) -> AgentRuntimeInstance | None:
        items = await self.list_by_agent_id(agent_id)
        if not items:
            return None
        canonical = items[0]
        if len(items) == 1:
            return canonical
        now = utcnow()
        for duplicate in items[1:]:
            duplicate.deleted_at = now
        await self._session.flush()
        return canonical

    async def dedupe_by_runtime_key(self, runtime_key: str) -> AgentRuntimeInstance | None:
        items = await self.list_by_runtime_key(runtime_key)
        if not items:
            return None
        canonical = items[0]
        if len(items) == 1:
            return canonical
        now = utcnow()
        for duplicate in items[1:]:
            duplicate.deleted_at = now
        await self._session.flush()
        return canonical

    async def ensure_for_agent(self, agent: AgentDefinition) -> AgentRuntimeInstance:
        runtime_key = f"{agent.name}:{agent.subgraph_key}"
        existing = await self.dedupe_by_agent_id(str(agent.id))
        if not existing:
            existing = await self.dedupe_by_runtime_key(runtime_key)
        if existing:
            existing.agent_id = str(agent.id)
            existing.runtime_key = runtime_key
            existing.subgraph_key = str(agent.subgraph_key or "quality_judgement")
            existing.supports_start_stop = bool(agent.supports_start_stop)
            existing.metadata_json = {"entry_graph": agent.entry_graph, "graph_version": agent.graph_version}
            if not getattr(existing, "status", None):
                existing.status = "running" if agent.is_active else "stopped"
            if not getattr(existing, "runtime_status", None):
                existing.runtime_status = "running" if agent.is_active else "stopped"
            await self._session.flush()
            return existing
        obj = AgentRuntimeInstance(
            org_id=self._org_id,
            agent_id=str(agent.id),
            runtime_key=runtime_key,
            subgraph_key=str(agent.subgraph_key or "quality_judgement"),
            status="running" if agent.is_active else "stopped",
            runtime_status="running" if agent.is_active else "stopped",
            supports_start_stop=bool(agent.supports_start_stop),
            metadata_json={"entry_graph": agent.entry_graph, "graph_version": agent.graph_version},
        )
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj, attribute_names=["created_at", "updated_at"])
        return obj

    async def list_with_agents(self) -> list[tuple[AgentRuntimeInstance, AgentDefinition]]:
        result = await self._session.execute(
            select(AgentRuntimeInstance, AgentDefinition)
            .join(AgentDefinition, AgentDefinition.id == AgentRuntimeInstance.agent_id)
            .where(
                AgentRuntimeInstance.org_id == self._org_id,
                AgentRuntimeInstance.deleted_at.is_(None),
                AgentDefinition.deleted_at.is_(None),
            )
            .order_by(AgentDefinition.created_at.desc())
        )
        return list(result.all())

    async def set_status(self, runtime_key: str, status: str) -> AgentRuntimeInstance | None:
        obj = await self.dedupe_by_runtime_key(runtime_key)
        if not obj:
            return None
        obj.status = status
        if status == "running":
            obj.last_started_at = utcnow()
        if status == "stopped":
            obj.last_stopped_at = utcnow()
        await self._session.flush()
        return obj

    async def create_event(self, data: dict):
        from app.models.agent_ops import AgentRuntimeEvent
        obj = AgentRuntimeEvent(org_id=self._org_id, **data)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def list_events(self, agent_id: str, limit: int = 20):
        from app.models.agent_ops import AgentRuntimeEvent
        result = await self._session.execute(
            select(AgentRuntimeEvent).where(
                AgentRuntimeEvent.org_id == self._org_id,
                AgentRuntimeEvent.agent_id == agent_id,
                AgentRuntimeEvent.deleted_at.is_(None),
            ).order_by(AgentRuntimeEvent.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def set_runtime_status(self, runtime_key: str, runtime_status: str, *, updated_by: str | None = None):
        obj = await self.dedupe_by_runtime_key(runtime_key)
        if not obj:
            return None
        obj.status = runtime_status
        obj.runtime_status = runtime_status
        obj.updated_by = updated_by
        if runtime_status == "running":
            obj.last_started_at = utcnow()
        if runtime_status == "stopped":
            obj.last_stopped_at = utcnow()
        await self._session.flush()
        return obj


class AgentRouteLogRepository(AgentOpsRepository):
    """Repository for agent_route_logs — audit trail of routing decisions."""

    async def create(self, data: dict) -> AgentRouteLog:
        obj = AgentRouteLog(**data, org_id=self._org_id)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def list_by_session(
        self, session_id: str, *, limit: int = 50
    ) -> list[AgentRouteLog]:
        result = await self._session.execute(
            select(AgentRouteLog)
            .where(
                AgentRouteLog.org_id == self._org_id,
                AgentRouteLog.session_id == session_id,
                AgentRouteLog.deleted_at.is_(None),
            )
            .order_by(AgentRouteLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_agent(
        self, selected_agent: str, *, limit: int = 50
    ) -> list[AgentRouteLog]:
        result = await self._session.execute(
            select(AgentRouteLog)
            .where(
                AgentRouteLog.org_id == self._org_id,
                AgentRouteLog.selected_agent == selected_agent,
                AgentRouteLog.deleted_at.is_(None),
            )
            .order_by(AgentRouteLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class AgentRuntimeEventRepository(AgentOpsRepository):
    async def create(self, data: dict):
        from app.models.agent_ops import AgentRuntimeEvent
        obj = AgentRuntimeEvent(org_id=self._org_id, **data)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def list_by_agent(self, agent_id: str, limit: int = 20):
        from app.models.agent_ops import AgentRuntimeEvent
        result = await self._session.execute(
            select(AgentRuntimeEvent).where(
                AgentRuntimeEvent.org_id == self._org_id,
                AgentRuntimeEvent.agent_id == agent_id,
                AgentRuntimeEvent.deleted_at.is_(None),
            ).order_by(AgentRuntimeEvent.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
