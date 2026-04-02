from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypeVar

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_ops import AgentDefinition, IntentRoute, PromptVersion
from app.models.result import InspectionResult

T = TypeVar("T")


class AgentOpsRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def _get_by_id(self, model: type[T], id: str) -> T | None:
        result = await self._session.execute(
            select(model).where(model.org_id == self._org_id, model.id == id, model.deleted_at.is_(None))
        )
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
        obj.deleted_at = datetime.utcnow()
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
        obj.deleted_at = datetime.utcnow()
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
        obj.deleted_at = datetime.utcnow()
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
    async def get_rag_stats(self, days: int = 7) -> dict:
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        stmt = select(
            func.count().label("total_queries"),
            func.coalesce(func.avg(self._citations_count_expr()), 0.0).label("avg_hit_rate"),
            func.coalesce(
                func.sum(case((self._is_non_empty_citations_expr(), 1), else_=0)) /
                func.nullif(func.count(), 0),
                0.0
            ).label("citation_coverage"),
            func.sum(case((self._is_empty_citations_expr(), 1), else_=0)).label("empty_recall_count"),
            func.coalesce(func.avg(InspectionResult.latency_ms), 0.0).label("avg_latency_ms"),
        ).where(
            InspectionResult.org_id == self._org_id,
            InspectionResult.created_at >= cutoff_date,
        )

        result = (await self._session.execute(stmt)).one()
        total_queries = int(result.total_queries or 0)
        avg_hit_rate = (
            float(result.avg_hit_rate or 0.0) / 5.0 if total_queries > 0 else 0.0
        )
        return {
            "total_queries": total_queries,
            "avg_hit_rate": avg_hit_rate,
            "citation_coverage": float(result.citation_coverage or 0.0),
            "empty_recall_count": int(result.empty_recall_count or 0),
            "avg_latency_ms": float(result.avg_latency_ms or 0.0),
        }

    async def get_recent_rag_items(self, limit: int = 10) -> list[dict]:
        stmt = select(
            InspectionResult.id,
            InspectionResult.task_id,
            InspectionResult.citations,
            InspectionResult.latency_ms,
            InspectionResult.created_at,
        ).where(
            InspectionResult.org_id == self._org_id,
            InspectionResult.citations.isnot(None),
        ).order_by(
            InspectionResult.created_at.desc()
        ).limit(limit)

        results = (await self._session.execute(stmt)).all()
        items = []
        for row in results:
            hit_rate = self._calculate_hit_rate(row.citations)
            citation_coverage = 1.0 if row.citations and self._get_citations_count(row.citations) > 0 else 0.0
            items.append({
                "task_id": str(row.task_id),
                "hit_rate": hit_rate,
                "citation_coverage": citation_coverage,
                "latency_ms": row.latency_ms or 0,
                "created_at": row.created_at,
            })
        return items

    @staticmethod
    def _citations_count_expr():
        return func.coalesce(
            func.json_length(func.json_extract(InspectionResult.citations, "$.items")),
            0
        )

    @staticmethod
    def _is_non_empty_citations_expr():
        items_len = func.coalesce(
            func.json_length(func.json_extract(InspectionResult.citations, "$.items")),
            0
        )
        return (InspectionResult.citations.isnot(None)) & (items_len > 0)

    @staticmethod
    def _is_empty_citations_expr():
        items_len = func.coalesce(
            func.json_length(func.json_extract(InspectionResult.citations, "$.items")),
            0
        )
        return (InspectionResult.citations.is_(None)) | (items_len == 0)

    @staticmethod
    def _calculate_hit_rate(citations: dict | None) -> float:
        if not citations:
            return 0.0
        items = citations.get("items", []) if isinstance(citations, dict) else []
        return min(float(len(items)) / 5.0, 1.0)

    @staticmethod
    def _get_citations_count(citations: dict | None) -> int:
        if not citations:
            return 0
        items = citations.get("items", []) if isinstance(citations, dict) else []
        return len(items)
