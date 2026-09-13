from __future__ import annotations

import json
from typing import Any

from app.core.ids import uuid7
from app.models.memory import MemoryEvent
from app.repositories.memory_repo import (
    MemoryEventRepository,
    MemoryItemRepository,
    MemorySyncOutboxRepository,
    UnifiedMemoryGovernanceRepository,
)
from app.services.memory_vector_service import CANDIDATE_MEMORY_COLLECTION, MEMORY_COLLECTION


class MemoryStateTransitionService:
    """Centralizes memory state changes and external index sync requests."""

    VALID_ACTIONS = {"activate", "isolate", "delete", "degrade", "patch", "expire"}

    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id
        self._items = MemoryItemRepository(session, org_id)
        self._events = MemoryEventRepository(session, org_id)
        self._outbox = MemorySyncOutboxRepository(session, org_id)
        self._governance = UnifiedMemoryGovernanceRepository(session, org_id)

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

        transition_payload = dict(payload or {})
        scope = dict(getattr(item, "scope_json", None) or {})
        bindings = []
        if callable(getattr(self._session, "execute", None)):
            bindings = await self._governance.list_scope_bindings([memory_id])
        active_bindings = [row for row in bindings if row.binding_status == "active"]
        scope_bindings = [
            {
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
                "binding_kind": row.binding_kind,
                "binding_status": row.binding_status,
            }
            for row in bindings
        ]
        expires_at = getattr(item, "expires_at", None)
        qdrant_payload = {
            "collection": MEMORY_COLLECTION,
            "memory_id": memory_id,
            "org_id": self._org_id,
            "user_id": str(getattr(item, "user_id", None) or ""),
            "memory_type": str(getattr(item, "memory_type", "") or ""),
            "status": target_status,
            "summary": str(getattr(item, "content_summary", "") or ""),
            "trust_score": float(
                transition_payload.get("trust_score")
                if transition_payload.get("trust_score") is not None
                else getattr(item, "trust_score", 0) or 0
            ),
            "confidence": float(getattr(item, "confidence", 0) or 0),
            "expires_at": expires_at.isoformat() if expires_at else "",
            "product_line": str(
                getattr(item, "product_line", None)
                or scope.get("product_line")
                or ""
            ),
            "rag_space_id": str(
                getattr(item, "rag_space_id", None)
                or scope.get("rag_space_id")
                or ""
            ),
            "task_id": str(
                getattr(item, "task_id", None)
                or getattr(item, "source_task_id", None)
                or scope.get("task_id")
                or ""
            ),
            "extra_payload": {
                "scope_type": str(scope.get("scope_type") or ""),
                "scope_id": str(scope.get("scope_id") or ""),
                "review_status": str(getattr(item, "review_status", "") or "candidate"),
                "scope_bindings": scope_bindings,
                "applicability": dict(getattr(item, "applicability_json", None) or {}),
                "trace_id": trace_id or getattr(item, "trace_id", None),
                "promotion_score": transition_payload.get("promotion_score"),
            },
        }
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
                    payload={
                        "collection": CANDIDATE_MEMORY_COLLECTION,
                        "memory_id": memory_id,
                        "trace_id": trace_id,
                    },
                    trace_id=trace_id,
                )
        else:
            if previous_status == "candidate":
                delete_payload = {
                    "collection": CANDIDATE_MEMORY_COLLECTION,
                    "memory_id": memory_id,
                    "trace_id": trace_id,
                }
                await self._outbox.create_pending(
                    memory_id=memory_id,
                    action="DELETE_CANDIDATE_VECTOR",
                    target_backend="qdrant",
                    payload=delete_payload,
                    trace_id=trace_id,
                )
            else:
                delete_payload = {
                    "collection": MEMORY_COLLECTION,
                    "memory_id": memory_id,
                    "trace_id": trace_id,
                }
                await self._outbox.create_pending(
                    memory_id=memory_id,
                    action="DELETE_ACTIVE_VECTOR",
                    target_backend="qdrant",
                    payload=delete_payload,
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
                "trust_score": float(
                    transition_payload.get("trust_score")
                    if transition_payload.get("trust_score") is not None
                    else getattr(item, "trust_score", 0) or 0
                ),
                "confidence": float(getattr(item, "confidence", 0) or 0),
                "scope_key": "|".join(
                    f"{row.scope_type}:{row.scope_id}" for row in active_bindings
                ) or (
                    f"{scope.get('scope_type')}:{scope.get('scope_id')}"
                    if scope.get("scope_type") and scope.get("scope_id")
                    else ""
                ),
                "review_status": str(getattr(item, "review_status", "") or "candidate"),
                "origin_kind": str((getattr(item, "content_json", None) or {}).get("source_type") or "unknown"),
                "scope_bindings_json": json.dumps(scope_bindings, ensure_ascii=False),
                "applicability_json": json.dumps(
                    dict(getattr(item, "applicability_json", None) or {}),
                    ensure_ascii=False,
                ),
                "sync_version": 2,
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
