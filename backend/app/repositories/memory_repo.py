from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import (
    MemoryDependencyEdge,
    MemoryEvaluation,
    MemoryEvent,
    MemoryItem,
    MemoryPolicy,
    MemoryRollback,
)


class MemoryItemRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def create(self, item: MemoryItem) -> MemoryItem:
        self._session.add(item)
        await self._session.flush()
        return item

    async def get_by_memory_id(self, memory_id: str) -> MemoryItem | None:
        result = await self._session.execute(
            select(MemoryItem).where(
                MemoryItem.org_id == self._org_id,
                MemoryItem.memory_id == memory_id,
                MemoryItem.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_org(
        self,
        status: str | None = None,
        memory_type: str | None = None,
        workspace: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryItem]:
        stmt = select(MemoryItem).where(
            MemoryItem.org_id == self._org_id,
            MemoryItem.deleted_at.is_(None),
        )
        if status:
            stmt = stmt.where(MemoryItem.status == status)
        if memory_type:
            stmt = stmt.where(MemoryItem.memory_type == memory_type)
        if workspace:
            stmt = stmt.where(MemoryItem.workspace == workspace)
        if user_id:
            stmt = stmt.where(MemoryItem.user_id == user_id)
        stmt = stmt.order_by(MemoryItem.updated_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_by_scope(
        self,
        workspace: str,
        memory_types: list[str] | None = None,
        user_id: str | None = None,
        task_id: str | None = None,
        limit: int = 50,
    ) -> list[MemoryItem]:
        stmt = select(MemoryItem).where(
            MemoryItem.org_id == self._org_id,
            MemoryItem.workspace == workspace,
            MemoryItem.status == "active",
            MemoryItem.deleted_at.is_(None),
            MemoryItem.expires_at.is_(None)
            | (MemoryItem.expires_at > datetime.now(timezone.utc)),
        )
        if memory_types:
            stmt = stmt.where(MemoryItem.memory_type.in_(memory_types))
        if user_id:
            stmt = stmt.where(
                (MemoryItem.user_id == user_id) | (MemoryItem.user_id.is_(None))
            )
        if task_id:
            stmt = stmt.where(MemoryItem.scope_json.contains({"task_id": task_id}))
        stmt = stmt.order_by(MemoryItem.updated_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, memory_id: str, status: str) -> None:
        values: dict[str, Any] = {"status": status}
        if status in ("deleted", "expired"):
            values["deleted_at"] = datetime.now(timezone.utc)
        stmt = (
            update(MemoryItem)
            .where(
                MemoryItem.org_id == self._org_id,
                MemoryItem.memory_id == memory_id,
                MemoryItem.deleted_at.is_(None),
            )
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def update_trust_score(self, memory_id: str, trust_score: float) -> None:
        stmt = (
            update(MemoryItem)
            .where(
                MemoryItem.org_id == self._org_id,
                MemoryItem.memory_id == memory_id,
                MemoryItem.deleted_at.is_(None),
            )
            .values(trust_score=trust_score)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def batch_update_status(self, memory_ids: list[str], status: str) -> int:
        values: dict[str, Any] = {"status": status}
        if status in ("deleted", "expired"):
            values["deleted_at"] = datetime.now(timezone.utc)
        stmt = (
            update(MemoryItem)
            .where(
                MemoryItem.org_id == self._org_id,
                MemoryItem.memory_id.in_(memory_ids),
                MemoryItem.deleted_at.is_(None),
            )
            .values(**values)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def soft_delete(self, memory_id: str) -> None:
        stmt = (
            update(MemoryItem)
            .where(
                MemoryItem.org_id == self._org_id,
                MemoryItem.memory_id == memory_id,
                MemoryItem.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(timezone.utc), status="deleted")
        )
        await self._session.execute(stmt)
        await self._session.flush()


class MemoryEventRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def create(self, event: MemoryEvent) -> MemoryEvent:
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_by_org(
        self,
        memory_id: str | None = None,
        event_type: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEvent]:
        stmt = select(MemoryEvent).where(
            MemoryEvent.org_id == self._org_id,
        )
        if memory_id:
            stmt = stmt.where(MemoryEvent.memory_id == memory_id)
        if event_type:
            stmt = stmt.where(MemoryEvent.event_type == event_type)
        if trace_id:
            stmt = stmt.where(MemoryEvent.trace_id == trace_id)
        stmt = stmt.order_by(MemoryEvent.created_at.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_event_id(self, event_id: str) -> MemoryEvent | None:
        result = await self._session.execute(
            select(MemoryEvent).where(
                MemoryEvent.org_id == self._org_id,
                MemoryEvent.event_id == event_id,
            )
        )
        return result.scalar_one_or_none()


class MemoryDependencyRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def create(self, edge: MemoryDependencyEdge) -> MemoryDependencyEdge:
        self._session.add(edge)
        await self._session.flush()
        return edge

    async def list_by_source(self, source_memory_id: str) -> list[MemoryDependencyEdge]:
        result = await self._session.execute(
            select(MemoryDependencyEdge).where(
                MemoryDependencyEdge.org_id == self._org_id,
                MemoryDependencyEdge.source_memory_id == source_memory_id,
                MemoryDependencyEdge.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_by_target(self, target_memory_id: str) -> list[MemoryDependencyEdge]:
        result = await self._session.execute(
            select(MemoryDependencyEdge).where(
                MemoryDependencyEdge.org_id == self._org_id,
                MemoryDependencyEdge.target_memory_id == target_memory_id,
                MemoryDependencyEdge.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_by_edge_type(
        self, memory_id: str, edge_types: list[str], direction: str = "source"
    ) -> list[MemoryDependencyEdge]:
        if direction == "source":
            stmt = select(MemoryDependencyEdge).where(
                MemoryDependencyEdge.org_id == self._org_id,
                MemoryDependencyEdge.source_memory_id == memory_id,
                MemoryDependencyEdge.edge_type.in_(edge_types),
                MemoryDependencyEdge.deleted_at.is_(None),
            )
        else:
            stmt = select(MemoryDependencyEdge).where(
                MemoryDependencyEdge.org_id == self._org_id,
                MemoryDependencyEdge.target_memory_id == memory_id,
                MemoryDependencyEdge.edge_type.in_(edge_types),
                MemoryDependencyEdge.deleted_at.is_(None),
            )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete_by_memory(self, memory_id: str) -> int:
        stmt = (
            update(MemoryDependencyEdge)
            .where(
                MemoryDependencyEdge.org_id == self._org_id,
                (
                    (MemoryDependencyEdge.source_memory_id == memory_id)
                    | (MemoryDependencyEdge.target_memory_id == memory_id)
                ),
                MemoryDependencyEdge.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(timezone.utc))
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount


class MemoryPolicyRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def create(self, policy: MemoryPolicy) -> MemoryPolicy:
        self._session.add(policy)
        await self._session.flush()
        return policy

    async def get_active(self, policy_key: str, policy_type: str) -> MemoryPolicy | None:
        result = await self._session.execute(
            select(MemoryPolicy)
            .where(
                MemoryPolicy.org_id == self._org_id,
                MemoryPolicy.policy_key == policy_key,
                MemoryPolicy.policy_type == policy_type,
                MemoryPolicy.status == "active",
                MemoryPolicy.deleted_at.is_(None),
            )
            .order_by(MemoryPolicy.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(self, workspace: str) -> list[MemoryPolicy]:
        result = await self._session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.org_id == self._org_id,
                MemoryPolicy.workspace == workspace,
                MemoryPolicy.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def update_status(self, policy_key: str, status: str) -> None:
        stmt = (
            update(MemoryPolicy)
            .where(
                MemoryPolicy.org_id == self._org_id,
                MemoryPolicy.policy_key == policy_key,
                MemoryPolicy.deleted_at.is_(None),
            )
            .values(status=status)
        )
        await self._session.execute(stmt)
        await self._session.flush()


class MemoryRollbackRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def create(self, rollback: MemoryRollback) -> MemoryRollback:
        self._session.add(rollback)
        await self._session.flush()
        return rollback

    async def get_by_rollback_id(self, rollback_id: str) -> MemoryRollback | None:
        result = await self._session.execute(
            select(MemoryRollback).where(
                MemoryRollback.org_id == self._org_id,
                MemoryRollback.rollback_id == rollback_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_root_memory(self, root_memory_id: str) -> list[MemoryRollback]:
        result = await self._session.execute(
            select(MemoryRollback)
            .where(
                MemoryRollback.org_id == self._org_id,
                MemoryRollback.root_memory_id == root_memory_id,
            )
            .order_by(MemoryRollback.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_review_status(self, rollback_id: str, review_status: str) -> None:
        stmt = (
            update(MemoryRollback)
            .where(
                MemoryRollback.org_id == self._org_id,
                MemoryRollback.rollback_id == rollback_id,
            )
            .values(review_status=review_status)
        )
        await self._session.execute(stmt)
        await self._session.flush()


class MemoryEvaluationRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def create(self, evaluation: MemoryEvaluation) -> MemoryEvaluation:
        self._session.add(evaluation)
        await self._session.flush()
        return evaluation

    async def get_by_evaluation_id(self, evaluation_id: str) -> MemoryEvaluation | None:
        result = await self._session.execute(
            select(MemoryEvaluation).where(
                MemoryEvaluation.org_id == self._org_id,
                MemoryEvaluation.evaluation_id == evaluation_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_rollback(self, rollback_id: str) -> list[MemoryEvaluation]:
        result = await self._session.execute(
            select(MemoryEvaluation)
            .where(
                MemoryEvaluation.org_id == self._org_id,
                MemoryEvaluation.rollback_id == rollback_id,
            )
            .order_by(MemoryEvaluation.created_at.desc())
        )
        return list(result.scalars().all())
