from __future__ import annotations

from typing import Any

from app.core.ids import uuid7
from app.models.memory import MemoryEvent
from app.repositories.memory_repo import (
    MemoryEventRepository,
    MemoryItemRepository,
    MemorySyncOutboxRepository,
)


class MemoryStateTransitionService:
    """Centralizes memory state changes and external index sync requests."""

    VALID_ACTIONS = {"activate", "isolate", "delete", "degrade", "patch", "expire"}

    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id
        self._items = MemoryItemRepository(session, org_id)
        self._events = MemoryEventRepository(session, org_id)
        self._outbox = MemorySyncOutboxRepository(session, org_id)

    async def transition(
        self,
        memory_id: str,
        *,
        action: str,
        target_status: str,
        actor_id: str | None = None,
        trace_id: str | None = None,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        normalized = str(action or "").lower()
        if normalized not in self.VALID_ACTIONS:
            raise ValueError(f"Unsupported memory state transition: {action}")

        item = await self._items.get_by_memory_id(memory_id)
        if not item:
            raise ValueError(f"Memory {memory_id} not found")
        previous_status = getattr(item, "status", None)

        await self._items.update_status(memory_id, target_status)
        await self._events.create(
            MemoryEvent(
                id=str(uuid7()),
                event_id=f"evt_{uuid7()}",
                org_id=self._org_id,
                user_id=getattr(item, "user_id", None),
                event_type=f"memory_{normalized}",
                trace_id=trace_id or getattr(item, "trace_id", None),
                memory_id=memory_id,
                payload_json={
                    "from_status": previous_status,
                    "to_status": target_status,
                    "actor_id": actor_id,
                    "reason": reason,
                    **(payload or {}),
                },
            )
        )

        qdrant_payload = {"memory_id": memory_id, "trace_id": trace_id, **(payload or {})}
        if target_status == "active":
            await self._outbox.create_pending(
                memory_id=memory_id,
                action="UPSERT_ACTIVE_VECTOR",
                target_backend="qdrant",
                payload=qdrant_payload,
                trace_id=trace_id,
            )
            if previous_status == "candidate":
                await self._outbox.create_pending(
                    memory_id=memory_id,
                    action="DELETE_CANDIDATE_VECTOR",
                    target_backend="qdrant",
                    payload={"memory_id": memory_id, "trace_id": trace_id},
                    trace_id=trace_id,
                )
        else:
            if previous_status == "candidate":
                await self._outbox.create_pending(
                    memory_id=memory_id,
                    action="DELETE_CANDIDATE_VECTOR",
                    target_backend="qdrant",
                    payload=qdrant_payload,
                    trace_id=trace_id,
                )
            else:
                await self._outbox.create_pending(
                    memory_id=memory_id,
                    action="DELETE_ACTIVE_VECTOR",
                    target_backend="qdrant",
                    payload=qdrant_payload,
                    trace_id=trace_id,
                )
        await self._outbox.create_pending(
            memory_id=memory_id,
            action="UPDATE_MEMORY_NODE_STATUS",
            target_backend="neo4j",
            payload={
                "memory_id": memory_id,
                "org_id": self._org_id,
                "memory_type": getattr(item, "memory_type", ""),
                "status": target_status,
                "trust_score": float(getattr(item, "trust_score", 0) or 0),
                "confidence": float(getattr(item, "confidence", 0) or 0),
                "scope_key": "",
            },
            trace_id=trace_id,
        )
        if target_status in {"deleted", "isolated", "expired"}:
            await self._outbox.create_pending(
                memory_id=memory_id,
                action="SOFT_DELETE_MEMORY_EDGES",
                target_backend="neo4j",
                payload={"memory_id": memory_id},
                trace_id=trace_id,
            )
