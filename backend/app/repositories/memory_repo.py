from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import (
    MemoryCandidateSupport,
    MemoryDependencyEdge,
    MemoryEvaluation,
    MemoryEvent,
    MemoryItem,
    MemoryPolicy,
    MemoryRollback,
    MemorySyncOutbox,
)


class MemoryItemRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    @staticmethod
    def _scope_equals(field: str, value: str):
        return MemoryItem.scope_json[field].as_string() == value

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

    async def get_by_idempotency_key(self, idempotency_key: str) -> MemoryItem | None:
        result = await self._session.execute(
            select(MemoryItem).where(
                MemoryItem.org_id == self._org_id,
                MemoryItem.idempotency_key == idempotency_key,
                MemoryItem.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def find_candidate_by_key(
        self,
        *,
        memory_type: str,
        candidate_key: str,
        user_id: str | None = None,
        scope: dict | None = None,
    ) -> MemoryItem | None:
        stmt = select(MemoryItem).where(
            MemoryItem.org_id == self._org_id,
            MemoryItem.memory_type == memory_type,
            MemoryItem.status.in_(("candidate", "active")),
            MemoryItem.candidate_key == candidate_key,
            MemoryItem.deleted_at.is_(None),
        )
        if user_id:
            stmt = stmt.where((MemoryItem.user_id == user_id) | (MemoryItem.user_id.is_(None)))
        result = await self._session.execute(stmt.order_by(MemoryItem.updated_at.desc()).limit(1))
        return result.scalar_one_or_none()

    async def list_by_org(
        self,
        status: str | None = None,
        memory_type: str | None = None,
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
        if user_id:
            stmt = stmt.where(MemoryItem.user_id == user_id)
        stmt = stmt.order_by(MemoryItem.updated_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_by_scope(
        self,
        memory_types: list[str] | None = None,
        user_id: str | None = None,
        task_id: str | None = None,
        product_line: str | None = None,
        rag_space_id: str | None = None,
        limit: int = 50,
    ) -> list[MemoryItem]:
        stmt = select(MemoryItem).where(
            MemoryItem.org_id == self._org_id,
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
        else:
            stmt = stmt.where(MemoryItem.user_id.is_(None))
        if task_id:
            stmt = stmt.where(self._scope_equals("task_id", task_id))
        if product_line:
            stmt = stmt.where(self._scope_equals("product_line", product_line))
        if rag_space_id:
            stmt = stmt.where(self._scope_equals("rag_space_id", rag_space_id))
        # Exclude memories that are old versions (target of a version_of edge)
        from app.models.memory import MemoryDependencyEdge as MDE
        versioned_out = (
            select(MDE.target_memory_id)
            .where(
                MDE.org_id == self._org_id,
                MDE.edge_type == "version_of",
                MDE.deleted_at.is_(None),
            )
        )
        stmt = stmt.where(MemoryItem.memory_id.not_in(versioned_out))
        stmt = stmt.order_by(MemoryItem.updated_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_retrievable_by_scope(
        self,
        memory_types: list[str] | None = None,
        user_id: str | None = None,
        task_id: str | None = None,
        product_line: str | None = None,
        rag_space_id: str | None = None,
        limit: int = 50,
    ) -> list[MemoryItem]:
        """Retrievable shared memory is active only."""
        stmt = select(MemoryItem).where(
            MemoryItem.org_id == self._org_id,
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
        else:
            stmt = stmt.where(MemoryItem.user_id.is_(None))
        if task_id:
            stmt = stmt.where(self._scope_equals("task_id", task_id))
        if product_line:
            stmt = stmt.where(self._scope_equals("product_line", product_line))
        if rag_space_id:
            stmt = stmt.where(self._scope_equals("rag_space_id", rag_space_id))
        # Exclude old versions
        from app.models.memory import MemoryDependencyEdge as MDE
        versioned_out = (
            select(MDE.target_memory_id)
            .where(
                MDE.org_id == self._org_id,
                MDE.edge_type == "version_of",
                MDE.deleted_at.is_(None),
            )
        )
        stmt = stmt.where(MemoryItem.memory_id.not_in(versioned_out))
        stmt = stmt.order_by(MemoryItem.updated_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_promotion_candidates(
        self,
        *,
        limit: int = 100,
    ) -> list[MemoryItem]:
        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.org_id == self._org_id,
                MemoryItem.status == "candidate",
                MemoryItem.deleted_at.is_(None),
            )
            .order_by(MemoryItem.updated_at.desc())
            .limit(limit)
        )
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

    async def update_candidate_stats(self, memory_id: str, **values) -> MemoryItem | None:
        item = await self.get_by_memory_id(memory_id)
        if not item:
            return None

        for key, value in values.items():
            if key.endswith("_delta"):
                attr = key[: -len("_delta")]
                setattr(item, attr, int(getattr(item, attr, 0) or 0) + int(value or 0))
            elif hasattr(item, key):
                setattr(item, key, value)
        await self._session.flush()
        return item

    async def update_index_status(
        self,
        memory_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "index_status": status,
            "index_error": error,
            "last_indexed_at": datetime.now(timezone.utc),
        }
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


class MemoryCandidateSupportRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def create(self, support: MemoryCandidateSupport) -> MemoryCandidateSupport:
        self._session.add(support)
        await self._session.flush()
        return support

    async def list_by_candidate(self, candidate_memory_id: str) -> list[MemoryCandidateSupport]:
        result = await self._session.execute(
            select(MemoryCandidateSupport)
            .where(
                MemoryCandidateSupport.org_id == self._org_id,
                MemoryCandidateSupport.candidate_memory_id == candidate_memory_id,
            )
            .order_by(MemoryCandidateSupport.created_at.asc())
        )
        return list(result.scalars().all())

    async def stats_for_candidate(self, candidate_memory_id: str) -> dict[str, float | int]:
        supports = await self.list_by_candidate(candidate_memory_id)
        if not supports:
            return {
                "support_count": 0,
                "negative_count": 0,
                "conflict_count": 0,
                "rag_evidence_count": 0,
                "agent_verifier_count": 0,
                "unique_task_count": 0,
                "avg_confidence": 0.0,
            }

        return {
            "support_count": sum(1 for s in supports if s.support_type not in {"negative", "conflict"}),
            "negative_count": sum(1 for s in supports if s.support_type == "negative"),
            "conflict_count": sum(1 for s in supports if s.support_type == "conflict"),
            "rag_evidence_count": sum(1 for s in supports if s.support_type == "rag_evidence"),
            "agent_verifier_count": len({
                str(s.source_agent)
                for s in supports
                if s.support_type == "agent_verifier" and s.source_agent
            }),
            "unique_task_count": len({str(s.task_id) for s in supports if s.task_id}),
            "avg_confidence": (
                sum(float(s.confidence or 0) for s in supports) / len(supports)
            ),
        }


class MemoryDependencyRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    async def create(self, edge: MemoryDependencyEdge) -> MemoryDependencyEdge:
        self._session.add(edge)
        await self._session.flush()
        return edge

    async def get_active_edge(
        self,
        source_memory_id: str,
        target_memory_id: str,
        edge_type: str,
    ) -> MemoryDependencyEdge | None:
        result = await self._session.execute(
            select(MemoryDependencyEdge).where(
                MemoryDependencyEdge.org_id == self._org_id,
                MemoryDependencyEdge.source_memory_id == source_memory_id,
                MemoryDependencyEdge.target_memory_id == target_memory_id,
                MemoryDependencyEdge.edge_type == edge_type,
                MemoryDependencyEdge.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_edge(
        self,
        *,
        source_memory_id: str,
        target_memory_id: str,
        edge_type: str,
        strength: float = 1.0,
        source_event_id: str | None = None,
        target_event_id: str | None = None,
        scope_json: dict | None = None,
        metadata_json: dict | None = None,
    ) -> MemoryDependencyEdge:
        existing = await self.get_active_edge(
            source_memory_id=source_memory_id,
            target_memory_id=target_memory_id,
            edge_type=edge_type,
        )

        if existing:
            existing.strength = max(float(existing.strength or 0), strength)
            existing.metadata_json = self._merge_edge_metadata(
                existing.metadata_json,
                metadata_json,
            )
            if source_event_id:
                existing.source_event_id = source_event_id
            if target_event_id:
                existing.target_event_id = target_event_id
            if scope_json:
                existing.scope_json = scope_json
            await self._session.flush()
            return existing

        from app.core.ids import uuid7
        edge = MemoryDependencyEdge(
            id=str(uuid7()),
            org_id=self._org_id,
            source_memory_id=source_memory_id,
            target_memory_id=target_memory_id,
            source_event_id=source_event_id,
            target_event_id=target_event_id,
            edge_type=edge_type,
            strength=strength,
            scope_json=scope_json,
            metadata_json=metadata_json,
        )
        return await self.create(edge)

    @staticmethod
    def _merge_edge_metadata(old: dict | None, new: dict | None) -> dict:
        from datetime import datetime, timezone
        merged = dict(old or {})
        incoming = dict(new or {})

        observed_count = int(merged.get("observed_count") or 1)
        incoming_count = int(incoming.get("observed_count") or 1)

        merged.update(incoming)
        merged["observed_count"] = observed_count + incoming_count
        merged["last_observed_at"] = incoming.get("last_observed_at") or datetime.now(timezone.utc).isoformat()

        return merged

    async def list_upstream(self, memory_id: str) -> list[MemoryDependencyEdge]:
        """Return edges where memory_id is the source (who this memory depends on)."""
        return await self.list_by_source(memory_id)

    async def list_downstream(self, memory_id: str) -> list[MemoryDependencyEdge]:
        """Return edges where memory_id is the target (who depends on this memory)."""
        return await self.list_by_target(memory_id)

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

    async def soft_delete_edges_between(
        self,
        source_memory_id: str,
        target_memory_id: str,
        edge_type: str,
    ) -> int:
        stmt = (
            update(MemoryDependencyEdge)
            .where(
                MemoryDependencyEdge.org_id == self._org_id,
                MemoryDependencyEdge.edge_type == edge_type,
                MemoryDependencyEdge.deleted_at.is_(None),
                (
                    (
                        (MemoryDependencyEdge.source_memory_id == source_memory_id)
                        & (MemoryDependencyEdge.target_memory_id == target_memory_id)
                    )
                    | (
                        (MemoryDependencyEdge.source_memory_id == target_memory_id)
                        & (MemoryDependencyEdge.target_memory_id == source_memory_id)
                    )
                ),
            )
            .values(deleted_at=datetime.now(timezone.utc))
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def list_all(self, *, org_id: str) -> list[MemoryDependencyEdge]:
        stmt = (
            select(MemoryDependencyEdge)
            .where(MemoryDependencyEdge.org_id == org_id)
            .where(MemoryDependencyEdge.deleted_at.is_(None))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


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

    async def list_all(self) -> list[MemoryPolicy]:
        result = await self._session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.org_id == self._org_id,
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

    async def update_execution_status(
        self,
        rollback_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        stmt = (
            update(MemoryRollback)
            .where(
                MemoryRollback.org_id == self._org_id,
                MemoryRollback.rollback_id == rollback_id,
            )
            .values(execution_status=status, execution_error=error)
        )
        await self._session.execute(stmt)
        await self._session.flush()


class MemorySyncOutboxRepository:
    def __init__(self, session: AsyncSession, org_id: str):
        self._session = session
        self._org_id = org_id

    @staticmethod
    async def list_pending_org_ids(session: AsyncSession, *, max_retries: int) -> list[str]:
        result = await session.execute(
            select(MemorySyncOutbox.org_id)
            .where(
                MemorySyncOutbox.status == "pending",
                MemorySyncOutbox.retry_count < max_retries,
            )
            .distinct()
            .order_by(MemorySyncOutbox.org_id.asc())
        )
        return [str(org_id) for org_id in result.scalars().all()]

    async def create_pending(
        self,
        *,
        memory_id: str,
        action: str,
        target_backend: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> MemorySyncOutbox:
        from app.core.ids import uuid7

        outbox = MemorySyncOutbox(
            id=str(uuid7()),
            org_id=self._org_id,
            memory_id=memory_id,
            action=action,
            target_backend=target_backend,
            payload_json=payload,
            status="pending",
            retry_count=0,
            trace_id=trace_id,
        )
        self._session.add(outbox)
        await self._session.flush()
        return outbox

    async def claim_pending(self, *, limit: int, max_retries: int) -> list[MemorySyncOutbox]:
        result = await self._session.execute(
            select(MemorySyncOutbox)
            .where(
                MemorySyncOutbox.org_id == self._org_id,
                MemorySyncOutbox.status == "pending",
                MemorySyncOutbox.retry_count < max_retries,
            )
            .order_by(MemorySyncOutbox.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_success(self, outbox_id: str) -> None:
        await self._session.execute(
            update(MemorySyncOutbox)
            .where(MemorySyncOutbox.org_id == self._org_id, MemorySyncOutbox.id == outbox_id)
            .values(status="success", last_error=None)
        )
        await self._session.flush()

    async def mark_failed(self, outbox_id: str, error: str) -> None:
        await self._session.execute(
            update(MemorySyncOutbox)
            .where(MemorySyncOutbox.org_id == self._org_id, MemorySyncOutbox.id == outbox_id)
            .values(
                status="pending",
                retry_count=MemorySyncOutbox.retry_count + 1,
                last_error=error,
            )
        )
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
