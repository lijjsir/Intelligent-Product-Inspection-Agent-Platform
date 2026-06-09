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
    ConflictRelation,
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
    MemoryScope,
    EdgeType,
)
from app.services.memory_vector_service import MemoryVectorService, MemoryVectorServiceError


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

    async def _resolve_policy(self, policy_type: str) -> dict:
        """Load active policy config, falling back to defaults."""
        try:
            policy = await self._policy_repo.get_active(
                policy_key=policy_type,
                policy_type=policy_type,
            )
            if policy and policy.config_json:
                return {**policy.config_json, "version": str(policy.version)}
        except Exception:
            pass
        from agent.contracts.memory_contracts import MemoryPolicyContract
        return MemoryPolicyContract.defaults(policy_type)


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

        # 3. Load policy for write gate thresholds
        policy = await self._resolve_policy("write_gate")
        isolate_on_rag = bool(policy.get("isolate_on_rag_conflict", True))

        # 4. Check RAG / standard conflicts (policy-driven)
        if isolate_on_rag:
            if any("conflict_with_rag" in w.lower() or "conflict with rag" in w.lower() for w in request.content.warnings):
                return await self._isolate(request, ["conflicts_with_rag"])

        # 5. Determine trust_score
        trust_score = request.confidence
        if any("conflict" in w.lower() for w in request.content.warnings):
            trust_score *= 0.6

        # 6. Determine initial status from policy thresholds
        active_threshold = float(policy.get("min_confidence_for_active", 0.75))
        isolate_threshold = float(policy.get("isolate_threshold", 0.4))

        if trust_score >= active_threshold:
            status = MemoryStatus.ACTIVE
        elif trust_score >= isolate_threshold:
            status = MemoryStatus.ISOLATED
        else:
            status = MemoryStatus.CANDIDATE

        idempotency_key = f"{request.org_id}:{request.trace_id}:{request.memory_type.value}:{request.content.summary[:80]}"
        existing = await self._item_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return MemoryWriteResponse(
                memory_id=existing.memory_id,
                status=MemoryStatus(existing.status),
                trust_score=float(existing.trust_score) if existing.trust_score is not None else None,
                confidence=float(existing.confidence) if existing.confidence is not None else None,
                warnings=["idempotent_replay"],
                policy_key=existing.policy_key or "write_gate",
                policy_version=existing.policy_version or str(policy.get("version", "default:v1")),
            )

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
            idempotency_key=idempotency_key,
            source_trace_id=request.source.trace_id or request.trace_id,
            source_task_id=request.source.task_id,
            index_status="pending",
            index_error=None,
            policy_key="write_gate",
            policy_version=str(policy.get("version", "default:v1")),
            last_accessed_at=datetime.now(timezone.utc),
            access_count=0,
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

        # 9. Sync to Qdrant with index_status tracking
        if self._vector and status == MemoryStatus.ACTIVE:
            try:
                scope = request.scope or MemoryScope()
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
                    product_line=scope.product_line or "",
                    rag_space_id=scope.rag_space_id or "",
                    task_id=scope.task_id or "",
                )
                await self._item_repo.update_index_status(memory_id, "success")
            except Exception as exc:
                error = str(exc)
                await self._item_repo.update_index_status(memory_id, "failed", error)
                await self._record_event(
                    event_type=EventType.MEMORY_WRITE_CREATED,
                    memory_id=memory_id,
                    trace_id=request.trace_id,
                    user_id=request.user_id,
                    workspace=request.workspace,
                    source_kind=request.source.kind,
                    payload={"qdrant_sync_failed": error},
                )
                warnings.append("qdrant_sync_failed")

        return MemoryWriteResponse(
            memory_id=memory_id,
            status=status,
            trust_score=trust_score,
            confidence=request.confidence,
            warnings=warnings,
            policy_key="write_gate",
            policy_version=str(policy.get("version", "default:v1")),
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
        idempotency_key = f"{request.org_id}:{request.trace_id}:{request.memory_type.value}:{request.content.summary[:80]}"
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
            idempotency_key=idempotency_key,
            source_trace_id=request.source.trace_id or request.trace_id if request.source else request.trace_id,
            source_task_id=request.source.task_id if request.source else None,
            index_status="pending",
            last_accessed_at=datetime.now(timezone.utc),
            access_count=0,
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
        """Controlled retrieval: MySQL pre-filter -> Qdrant semantic recall -> MySQL verify -> rerank."""

        memory_types = (
            [mt.value for mt in request.scope_filter.memory_type]
            if request.scope_filter and request.scope_filter.memory_type
            else None
        )

        # 1. Load retrieval policy
        policy = await self._resolve_policy("retrieval")
        max_top_k = int(policy.get("max_top_k", 10))
        effective_top_k = min(request.top_k, max_top_k)

        # 2. MySQL: get eligible memories (tenant + scope + status + TTL)
        eligible = await self._item_repo.list_active_by_scope(
            workspace=request.workspace.value,
            memory_types=memory_types,
            user_id=request.user_id,
            task_id=request.scope_filter.task_id if request.scope_filter else None,
            product_line=request.scope_filter.product_line if request.scope_filter else None,
            rag_space_id=request.scope_filter.rag_space_id if request.scope_filter else None,
            limit=100,
        )

        if not eligible:
            return MemorySearchResponse(
                items=[],
                policy_version="default:v1",
                trace_id=request.trace_id,
            )

        # 2. Qdrant semantic recall — over-fetch then MySQL verify
        if self._vector is None:
            raise MemoryVectorServiceError("vector service is required for shared memory search")

        items: list[MemorySearchItem] = []
        if self._vector:
            semantic_top_k = min(effective_top_k * 10, 100)
            vector_results = await self._vector.search(
                query=request.query,
                org_id=request.org_id,
                workspace=request.workspace.value,
                top_k=semantic_top_k,
                user_id=request.user_id,
                memory_types=memory_types,
                product_line=request.scope_filter.product_line if request.scope_filter else None,
                rag_space_id=request.scope_filter.rag_space_id if request.scope_filter else None,
                task_id=request.scope_filter.task_id if request.scope_filter else None,
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
            # Rerank: vector_score * 0.55 + trust_score * 0.30 + confidence * 0.15
            items.sort(
                key=lambda x: (x.score or 0) * 0.55
                + (x.trust_score or 0) * 0.30
                + (x.confidence or 0) * 0.15,
                reverse=True,
            )
            items = items[:effective_top_k]
        else:
            items = self._fallback_search(eligible, request.query, request.top_k)

        # 2a. Conflict detection on recalled items
        conflict_info: dict = {}
        if items and len(items) >= 2:
            try:
                from app.services.memory_conflict_service import ConflictDetectionService
                detector = ConflictDetectionService(
                    org_id=self._org_id,
                    user_id=request.user_id,
                    trace_id=request.trace_id,
                )
                item_dicts = [
                    {
                        "memory_id": item.memory_id,
                        "summary": item.summary,
                        "score": item.score,
                        "memory_type": item.memory_type,
                    }
                    for item in items
                ]
                detection = await detector.detect(item_dicts)

                if detection.contested_ids:
                    for item in items:
                        if item.memory_id in detection.contested_ids:
                            await self._item_repo.update_status(item.memory_id, "contested")

                    for pair in detection.pairs:
                        if pair.relation == ConflictRelation.CONTRADICTS:
                            await self._dep_repo.create(MemoryDependencyEdge(
                                id=str(uuid7()),
                                org_id=self._org_id,
                                source_memory_id=pair.source_memory_id,
                                target_memory_id=pair.target_memory_id,
                                edge_type=EdgeType.CONFLICTS_WITH.value,
                                strength=1.0,
                            ))
                            await self._dep_repo.create(MemoryDependencyEdge(
                                id=str(uuid7()),
                                org_id=self._org_id,
                                source_memory_id=pair.target_memory_id,
                                target_memory_id=pair.source_memory_id,
                                edge_type=EdgeType.CONFLICTS_WITH.value,
                                strength=1.0,
                            ))
                            await self._record_event(
                                event_type=EventType.MEMORY_CONFLICT_DETECTED,
                                memory_id=pair.source_memory_id,
                                trace_id=request.trace_id,
                                payload={
                                    "conflict_with": pair.target_memory_id,
                                    "relation": pair.relation.value,
                                },
                            )

                        elif pair.relation == ConflictRelation.REFINES:
                            await self._dep_repo.create(MemoryDependencyEdge(
                                id=str(uuid7()),
                                org_id=self._org_id,
                                source_memory_id=pair.target_memory_id,
                                target_memory_id=pair.source_memory_id,
                                edge_type=EdgeType.DERIVED_FROM.value,
                                strength=0.8,
                            ))

                conflict_info = {
                    "contested_count": len(detection.contested_ids),
                    "refine_count": len(detection.refine_pairs),
                }
            except Exception:
                logger.debug("Conflict detection skipped", exc_info=True)

        # 3. Record retrieval event
        await self._record_event(
            event_type=EventType.MEMORY_RETRIEVAL_COMPLETED,
            user_id=request.user_id,
            workspace=request.workspace,
            payload={
                "query": request.query,
                "top_k": request.top_k,
                "result_count": len(items),
            },
        )

        return MemorySearchResponse(
            items=items,
            policy_version=f"retrieval:v{policy.get('version', '1')}",
            trace_id=request.trace_id,
            conflict_info=conflict_info if conflict_info else None,
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
