"""MemoryService - write gate, retrieval, status management, event recording.

Orchestrates MySQL persistence via repositories and Qdrant indexing via MemoryVectorService.
Never bypassed by LangGraph nodes or tools.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.core.ids import uuid7
from app.models.memory import (
    MemoryDependencyEdge,
    MemoryEvent,
    MemoryItem,
)
from app.repositories.memory_repo import (
    MemoryDependencyRepository,
    MemoryEventRepository,
    MemoryItemRepository,
    MemoryPolicyRepository,
)
from app.schemas.memory import (
    EventType,
    MemoryEventPayload,
    MemorySearchResponse,
    MemoryType,
    MemoryWriteRequest,
    MemoryWriteResponse,
    MemoryStatus,
    MemorySearchRequest,
    MemorySearchItem,
    ScopeFilter,
    EdgeType,
)
from app.services.memory_vector_service import MemoryVectorService


class MemoryService:
    """Central service for shared memory write gate, retrieval, and lifecycle."""

    def __init__(
        self,
        session,
        org_id: str,
        vector_service: MemoryVectorService | None = None,
    ):
        self._session = session
        self._org_id = org_id
        self._item_repo = MemoryItemRepository(session, org_id)
        self._event_repo = MemoryEventRepository(session, org_id)
        self._dep_repo = MemoryDependencyRepository(session, org_id)
        self._policy_repo = MemoryPolicyRepository(session, org_id)
        self._vector = vector_service

    # ------------------------------------------------------------------
    # Write Gate
    # ------------------------------------------------------------------

    async def write_candidate(self, request: MemoryWriteRequest) -> MemoryWriteResponse:
        """Process a candidate memory through the write gate."""
        warnings: list[str] = []

        # 1. Reject missing required fields
        if not request.trace_id:
            return await self._reject(request, "missing trace_id")
        if not request.source or not request.source.kind:
            return await self._reject(request, "missing source")

        # 2. Check for sensitive content
        sens_check = self._check_sensitive(request.content.summary)
        if sens_check:
            return await self._reject(request, f"sensitive content: {sens_check}")

        # 3. Check RAG / standard conflicts
        if any("conflict_with_rag" in w.lower() or "conflict with rag" in w.lower() for w in request.content.warnings):
            return await self._isolate(request, ["conflicts_with_rag"])

        # 4. Determine trust_score
        trust_score = request.confidence
        if any("conflict" in w.lower() for w in request.content.warnings):
            trust_score *= 0.6

        # 5. Determine initial status
        if trust_score >= 0.75:
            status = MemoryStatus.ACTIVE
        elif trust_score >= 0.4:
            status = MemoryStatus.ISOLATED
        else:
            status = MemoryStatus.CANDIDATE

        # 6. Generate memory_id
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"

        # 7. Persist to MySQL
        expires_at = self._ttl_expiry(request.ttl_policy)
        item = MemoryItem(
            id=str(uuid7()),
            memory_id=memory_id,
            org_id=request.org_id,
            user_id=request.user_id,
            workspace=request.workspace.value,
            memory_type=request.memory_type.value,
            scope_json=request.scope.model_dump() if request.scope else None,
            content_summary=request.content.summary,
            content_json={
                "facts": request.content.facts,
                "preferences": request.content.preferences,
                "warnings": request.content.warnings,
                "risk_notes": request.content.risk_notes,
            },
            source_event_ids=[request.trace_id] if request.trace_id else None,
            evidence_pointers=request.evidence_pointers,
            version_parent_id=request.version_parent_id,
            trust_score=trust_score,
            confidence=request.confidence,
            usage_policy="context_only",
            ttl_policy=request.ttl_policy,
            privacy_level=request.privacy_level.value if hasattr(request.privacy_level, 'value') else request.privacy_level,
            status=status.value,
            created_by=request.created_by,
            created_by_type=request.created_by_type,
            trace_id=request.trace_id,
            expires_at=expires_at,
        )
        await self._item_repo.create(item)

        # 8. Record event
        await self._record_event(
            event_type=(
                EventType.MEMORY_WRITE_CREATED
                if status == MemoryStatus.ACTIVE
                else EventType.MEMORY_CANDIDATE_CREATED
            ),
            memory_id=memory_id,
            trace_id=request.trace_id,
            user_id=request.user_id,
            workspace=request.workspace,
            source_kind=request.source.kind,
        )

        # 9. Sync to Qdrant (best effort)
        if self._vector and status == MemoryStatus.ACTIVE:
            try:
                await self._vector.upsert_memory(
                    memory_id=memory_id,
                    org_id=request.org_id,
                    user_id=request.user_id or "",
                    workspace=request.workspace.value,
                    memory_type=request.memory_type.value,
                    status=status.value,
                    summary=request.content.summary,
                    trust_score=trust_score,
                    confidence=request.confidence,
                    expires_at=expires_at.isoformat() if expires_at else "",
                )
            except Exception:
                warnings.append("qdrant_sync_failed")

        return MemoryWriteResponse(
            memory_id=memory_id,
            status=status,
            trust_score=trust_score,
            confidence=request.confidence,
            warnings=warnings,
        )

    async def _reject(self, request: MemoryWriteRequest, reason: str) -> MemoryWriteResponse:
        await self._record_event(
            event_type=EventType.MEMORY_WRITE_REJECTED,
            trace_id=request.trace_id,
            user_id=request.user_id,
            workspace=request.workspace,
            source_kind=request.source.kind if request.source else None,
            payload={"reason": reason},
        )
        return MemoryWriteResponse(
            memory_id="",
            status=MemoryStatus.CANDIDATE,
            trust_score=0.0,
            confidence=request.confidence,
            warnings=[reason],
        )

    async def _isolate(self, request: MemoryWriteRequest, warnings: list[str]) -> MemoryWriteResponse:
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        item = MemoryItem(
            id=str(uuid7()),
            memory_id=memory_id,
            org_id=request.org_id,
            user_id=request.user_id,
            workspace=request.workspace.value,
            memory_type=request.memory_type.value,
            scope_json=request.scope.model_dump() if request.scope else None,
            content_summary=request.content.summary,
            content_json={
                "facts": request.content.facts,
                "preferences": request.content.preferences,
                "warnings": request.content.warnings,
            },
            source_event_ids=[request.trace_id] if request.trace_id else None,
            evidence_pointers=request.evidence_pointers,
            confidence=request.confidence,
            trust_score=request.confidence * 0.3,
            status=MemoryStatus.ISOLATED.value,
            created_by_type=request.created_by_type,
            trace_id=request.trace_id,
            ttl_policy=request.ttl_policy,
            expires_at=self._ttl_expiry(request.ttl_policy),
        )
        await self._item_repo.create(item)
        await self._record_event(
            event_type=EventType.MEMORY_CANDIDATE_CREATED,
            memory_id=memory_id,
            trace_id=request.trace_id,
            workspace=request.workspace,
        )
        return MemoryWriteResponse(
            memory_id=memory_id,
            status=MemoryStatus.ISOLATED,
            trust_score=request.confidence * 0.3,
            confidence=request.confidence,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Controlled Retrieval
    # ------------------------------------------------------------------

    async def search(self, request: MemorySearchRequest) -> MemorySearchResponse:
        """Controlled retrieval: MySQL permission filter -> Qdrant semantic recall -> MySQL verify -> rerank."""
        warnings: list[str] = []
        degraded = False

        memory_types = (
            [mt.value for mt in request.scope_filter.memory_type]
            if request.scope_filter and request.scope_filter.memory_type
            else None
        )

        # 1. MySQL: get eligible memories (tenant + scope + status + TTL)
        eligible = await self._item_repo.list_active_by_scope(
            workspace=request.workspace.value,
            memory_types=memory_types,
            user_id=request.user_id,
            task_id=request.scope_filter.task_id if request.scope_filter else None,
            limit=100,
        )

        if not eligible:
            return MemorySearchResponse(
                items=[],
                degraded=False,
                warnings=["no_eligible_memories"],
            )

        # 2. Qdrant semantic recall
        items: list[MemorySearchItem] = []
        if self._vector:
            try:
                vector_results = await self._vector.search(
                    query=request.query,
                    org_id=request.org_id,
                    workspace=request.workspace.value,
                    top_k=request.top_k,
                )
                # Cross-reference with eligible memories from MySQL
                eligible_ids = {m.memory_id for m in eligible}
                for vr in vector_results:
                    if vr.get("memory_id") in eligible_ids:
                        match = next(
                            (m for m in eligible if m.memory_id == vr.get("memory_id")),
                            None,
                        )
                        if match:
                            items.append(self._to_search_item(match, vr.get("score", 0.0)))
            except Exception:
                degraded = True
                warnings.append("qdrant_degraded")
                items = self._fallback_search(eligible, request.query, request.top_k)
        else:
            items = self._fallback_search(eligible, request.query, request.top_k)

        # 3. Record retrieval event
        await self._record_event(
            event_type=EventType.MEMORY_RETRIEVAL_COMPLETED
            if not degraded
            else EventType.MEMORY_DEGRADED,
            user_id=request.user_id,
            workspace=request.workspace,
            payload={"query": request.query, "top_k": request.top_k, "result_count": len(items)},
        )

        return MemorySearchResponse(
            items=items,
            degraded=degraded,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Dependency Edges
    # ------------------------------------------------------------------

    async def record_dependency(
        self,
        source_memory_id: str,
        target_memory_id: str,
        edge_type: EdgeType,
        strength: float = 0.5,
        source_event_id: str | None = None,
        target_event_id: str | None = None,
    ) -> MemoryDependencyEdge:
        edge = MemoryDependencyEdge(
            id=str(uuid7()),
            org_id=self._org_id,
            source_memory_id=source_memory_id,
            target_memory_id=target_memory_id,
            source_event_id=source_event_id,
            target_event_id=target_event_id,
            edge_type=edge_type.value,
            strength=strength,
        )
        return await self._dep_repo.create(edge)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def record_event(self, payload: MemoryEventPayload) -> MemoryEvent:
        event = MemoryEvent(
            id=str(uuid7()),
            event_id=payload.event_id,
            org_id=payload.org_id,
            user_id=payload.user_id,
            workspace=payload.workspace.value,
            event_type=payload.event_type.value,
            source_kind=payload.source_kind,
            agent_id=payload.agent_id,
            role=payload.role,
            task_id=payload.task_id,
            trace_id=payload.trace_id,
            memory_id=payload.memory_id,
            payload_ref=payload.payload_ref,
            payload_json=payload.payload_json,
            risk_tags=payload.risk_tags,
            parent_event_ids=payload.parent_event_ids,
        )
        return await self._event_repo.create(event)

    async def get_events(
        self,
        memory_id: str | None = None,
        event_type: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEvent]:
        return await self._event_repo.list_by_org(
            memory_id=memory_id,
            event_type=event_type,
            trace_id=trace_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    async def update_status(self, memory_id: str, status: MemoryStatus) -> None:
        await self._item_repo.update_status(memory_id, status.value)
        if self._vector and status in (MemoryStatus.DELETED, MemoryStatus.DISABLED):
            try:
                await self._vector.delete_memory(memory_id)
            except Exception:
                pass

    async def batch_update_status(self, memory_ids: list[str], status: MemoryStatus) -> int:
        return await self._item_repo.batch_update_status(memory_ids, status.value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _record_event(
        self,
        event_type: EventType,
        memory_id: str | None = None,
        trace_id: str | None = None,
        user_id: str | None = None,
        workspace=None,
        source_kind: str | None = None,
        payload: dict | None = None,
    ) -> None:
        event = MemoryEvent(
            id=str(uuid7()),
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            org_id=self._org_id,
            user_id=user_id,
            workspace=workspace.value if hasattr(workspace, 'value') else (workspace or "app"),
            event_type=event_type.value,
            source_kind=source_kind,
            trace_id=trace_id,
            memory_id=memory_id,
            payload_json=payload,
        )
        await self._event_repo.create(event)

    @staticmethod
    def _check_sensitive(summary: str) -> str | None:
        import re
        if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', summary):
            return "email_detected"
        if re.search(r'\b1[3-9]\d{9}\b', summary):
            return "phone_detected"
        return None

    @staticmethod
    def _ttl_expiry(ttl_policy: str) -> datetime | None:
        if ttl_policy == "never":
            return None
        if ttl_policy == "task_only":
            return datetime.now(timezone.utc) + timedelta(hours=12)
        days = int(ttl_policy.replace("d", "")) if ttl_policy.endswith("d") else 90
        return datetime.now(timezone.utc) + timedelta(days=days)

    def _to_search_item(self, item: MemoryItem, score: float) -> MemorySearchItem:
        return MemorySearchItem(
            memory_id=item.memory_id,
            memory_type=item.memory_type,
            summary=item.content_summary or "",
            score=score,
            confidence=float(item.confidence) if item.confidence else None,
            trust_score=float(item.trust_score) if item.trust_score else None,
            source={
                "task_id": item.scope_json.get("task_id") if item.scope_json else None,
                "trace_id": item.trace_id,
            },
            usage_policy=item.usage_policy,
        )

    def _fallback_search(
        self, eligible: list[MemoryItem], query: str, top_k: int
    ) -> list[MemorySearchItem]:
        query_tokens = set(query.lower().split())
        scored = []
        for mem in eligible:
            summary = (mem.content_summary or "").lower()
            if not summary:
                continue
            mem_tokens = set(summary.split())
            if not query_tokens:
                continue
            jaccard = len(query_tokens & mem_tokens) / len(query_tokens | mem_tokens)
            confidence = float(mem.confidence) if mem.confidence else 0.5
            score = jaccard * 0.5 + confidence * 0.5
            scored.append((score, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._to_search_item(mem, score) for score, mem in scored[:top_k]]
