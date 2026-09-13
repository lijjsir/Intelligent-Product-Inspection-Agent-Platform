from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.ids import uuid7
from app.models.meeting import MemoryScopeBinding, MemoryTransferLog
from app.models.memory import MemoryItem
from app.repositories.memory_repo import (
    MemoryEvidenceRepository,
    MemoryItemRepository,
    MemoryOriginRepository,
    MemorySyncOutboxRepository,
    UnifiedMemoryGovernanceRepository,
)
from app.schemas.memory import (
    MemoryEvidenceDetailResponse,
    MemoryEvidenceItem,
    MemoryEvidenceSummary,
    MemoryOriginItem,
    MemoryReadinessResponse,
    MemoryScopeBindingItem,
    MemorySyncState,
    OrganizationGovernanceItem,
    OrganizationGovernanceResponse,
)
from app.services.memory_governance_domain import calculate_readiness
from app.services.memory_vector_service import MEMORY_COLLECTION


class UnifiedMemoryGovernanceService:
    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id
        self._items = MemoryItemRepository(session, org_id)
        self._origins = MemoryOriginRepository(session, org_id)
        self._evidence = MemoryEvidenceRepository(session, org_id)
        self._governance = UnifiedMemoryGovernanceRepository(session, org_id)
        self._outbox = MemorySyncOutboxRepository(session, org_id)

    async def organization_overview(self, *, limit: int = 100) -> OrganizationGovernanceResponse:
        pending_rows = await self._governance.list_pending_org_transfers(limit=limit)
        pending_items: list[MemoryItem] = []
        for row in pending_rows:
            item = await self._items.get_by_memory_id(str(row.memory_id))
            if item is not None:
                pending_items.append(item)
        promotion = await self._governance.list_promotion_candidates(limit=limit)
        active = await self._governance.list_active_org_memories(limit=limit)

        all_items = self._dedupe_items([*pending_items, *promotion, *active])
        maps = await self._related_maps(all_items)
        pending_by_memory = {str(row.memory_id): row for row in pending_rows}
        return OrganizationGovernanceResponse(
            pending_approval=[
                self._to_item(item, maps, share_request=pending_by_memory.get(item.memory_id))
                for item in pending_items
            ],
            promotion_candidates=[self._to_item(item, maps) for item in promotion],
            active=[self._to_item(item, maps) for item in active],
        )

    async def evidence_detail(self, memory_id: str) -> MemoryEvidenceDetailResponse:
        item = await self._items.get_by_memory_id(memory_id)
        if item is None:
            raise ValueError(f"Memory {memory_id} not found")
        origins = await self._origins.list_by_memory(memory_id)
        evidence = await self._evidence.list_by_memory(memory_id)
        scopes = await self._governance.list_scope_bindings([memory_id])
        return MemoryEvidenceDetailResponse(
            memory_id=memory_id,
            origins=[self._origin_item(row) for row in origins],
            evidence=[self._evidence_item(row) for row in evidence],
            scopes=[self._scope_item(row) for row in scopes],
            applicability=dict(item.applicability_json or {}),
            review_status=item.review_status,
            readiness_status=item.readiness_status,
            readiness_score=float(item.promotion_score or 0),
            readiness_blockers=[str(value) for value in list(item.readiness_blockers or [])],
        )

    async def evaluate_readiness(self, memory_id: str) -> MemoryReadinessResponse:
        item = await self._items.get_by_memory_id(memory_id)
        if item is None:
            raise ValueError(f"Memory {memory_id} not found")
        stats = await self._evidence.stats_for_memory(memory_id)
        readiness = calculate_readiness(
            stats,
            review_status=item.review_status,
            migration_review_required=bool(item.migration_review_required),
        )
        await self._items.update_candidate_stats(
            memory_id,
            origin_evidence_count=int(stats["origin_evidence_count"] or 0),
            independent_support_count=int(stats["independent_support_count"] or 0),
            support_count=int(stats["support_count"] or 0),
            rag_evidence_count=int(stats["rag_evidence_count"] or 0),
            agent_verifier_count=int(stats["agent_verifier_count"] or 0),
            human_confirmation_count=int(stats["human_confirmation_count"] or 0),
            opposition_count=int(stats["opposition_count"] or 0),
            negative_count=int(stats["opposition_count"] or 0),
            conflict_count=int(stats["conflict_count"] or 0),
            last_evidence_at=stats["last_evidence_at"],
            last_supported_at=stats["last_evidence_at"],
            readiness_status=readiness.status,
            readiness_blockers=readiness.blockers,
            promotion_score=readiness.score,
        )
        return MemoryReadinessResponse(
            memory_id=memory_id,
            review_status=item.review_status,
            readiness_status=readiness.status,
            readiness_score=readiness.score,
            readiness_reason=readiness.reason,
            blockers=readiness.blockers,
        )

    async def submit_organization_review(
        self,
        memory_id: str,
        *,
        requester_id: str,
        reason: str | None = None,
    ) -> str:
        readiness = await self.evaluate_readiness(memory_id)
        if readiness.readiness_status != "ready":
            raise ValueError(
                "Memory is not ready for organization review: "
                + ", ".join(readiness.blockers or ["evidence_threshold_not_met"])
            )
        item = await self._items.get_by_memory_id(memory_id)
        if item is None:
            raise ValueError(f"Memory {memory_id} not found")
        bindings = await self._governance.list_scope_bindings([memory_id])
        home = next(
            (row for row in bindings if row.binding_kind == "home" and row.binding_status == "active"),
            None,
        )
        if home is None:
            raise ValueError("Memory has no active home scope")
        pending = await self._governance.list_pending_org_transfers(limit=500)
        existing = next((row for row in pending if str(row.memory_id) == memory_id), None)
        if existing is not None:
            return str(existing.id)
        raw = f"{self._org_id}|{memory_id}|{home.scope_type}|{home.scope_id}|org_space"
        transfer = MemoryTransferLog(
            org_id=self._org_id,
            memory_id=memory_id,
            from_scope_type=home.scope_type,
            from_scope_id=home.scope_id,
            to_scope_type="org_space",
            to_scope_id=self._org_id,
            transfer_reason=reason or "证据达到组织审批条件",
            status="pending_approval",
            operator_id=requester_id,
            requested_by=requester_id,
            idempotency_key=f"org-review:{hashlib.sha256(raw.encode()).hexdigest()[:48]}",
        )
        self._session.add(transfer)
        await self._session.flush()
        return str(transfer.id)

    async def revoke_organization_binding(
        self,
        memory_id: str,
        *,
        operator_id: str,
        reason: str,
    ) -> int:
        item = await self._items.get_by_memory_id(memory_id)
        if item is None:
            raise ValueError(f"Memory {memory_id} not found")
        revoked_at = datetime.now(timezone.utc)
        count = await self._governance.revoke_org_binding(memory_id=memory_id, revoked_at=revoked_at)
        if count < 1:
            raise ValueError("Memory has no active organization binding")
        remaining = await self._governance.list_scope_bindings([memory_id])
        active = [row for row in remaining if row.binding_status == "active"]
        if active:
            await self._outbox.create_pending(
                memory_id=memory_id,
                action="UPSERT_ACTIVE_VECTOR",
                target_backend="qdrant",
                payload=self._vector_payload(item, active),
                trace_id=item.trace_id,
            )
        else:
            await self._outbox.create_pending(
                memory_id=memory_id,
                action="DELETE_ACTIVE_VECTOR",
                target_backend="qdrant",
                payload={"memory_id": memory_id, "trace_id": item.trace_id},
                trace_id=item.trace_id,
            )
        await self._outbox.create_pending(
            memory_id=memory_id,
            action="UPDATE_MEMORY_NODE_STATUS",
            target_backend="neo4j",
            payload={
                "memory_id": memory_id,
                "org_id": self._org_id,
                "memory_type": item.memory_type,
                "status": item.review_status,
                "trust_score": float(item.trust_score or 0),
                "confidence": float(item.confidence or 0),
                "scope_key": "|".join(f"{row.scope_type}:{row.scope_id}" for row in active),
                "review_status": item.review_status,
                "origin_kind": str((item.content_json or {}).get("source_type") or "unknown"),
                "scope_bindings_json": "[]",
                "applicability_json": "{}",
                "sync_version": 2,
            },
            trace_id=item.trace_id,
        )
        # A revoked target projection must not retain a live provenance edge
        # pointing into the retrievable graph.  Keep the MySQL audit records,
        # but let Neo4j soft-delete the active edges when no scope remains.
        if not active:
            await self._outbox.create_pending(
                memory_id=memory_id,
                action="SOFT_DELETE_MEMORY_EDGES",
                target_backend="neo4j",
                payload={"memory_id": memory_id},
                trace_id=item.trace_id,
            )
        return count

    async def _related_maps(self, items: list[MemoryItem]) -> dict[str, Any]:
        ids = [item.memory_id for item in items]
        origins = await self._origins.list_by_memories(ids)
        evidence = await self._evidence.list_by_memories(ids)
        scopes = await self._governance.list_scope_bindings(ids)
        origin_map: dict[str, list[Any]] = defaultdict(list)
        evidence_map: dict[str, list[Any]] = defaultdict(list)
        scope_map: dict[str, list[Any]] = defaultdict(list)
        for row in origins:
            origin_map[row.memory_id].append(row)
        for row in evidence:
            evidence_map[row.memory_id].append(row)
        for row in scopes:
            scope_map[row.memory_id].append(row)
        return {"origins": origin_map, "evidence": evidence_map, "scopes": scope_map}

    def _to_item(
        self,
        item: MemoryItem,
        maps: dict[str, Any],
        *,
        share_request: MemoryTransferLog | None = None,
    ) -> OrganizationGovernanceItem:
        origins = maps["origins"].get(item.memory_id, [])
        evidence_rows = maps["evidence"].get(item.memory_id, [])
        scopes = maps["scopes"].get(item.memory_id, [])
        home = next((row for row in scopes if row.binding_kind == "home"), None)
        target = next(
            (row for row in scopes if row.scope_type == "org_space" and row.binding_status == "active"),
            None,
        )
        evidence = self._evidence_summary(evidence_rows)
        if share_request is not None and target is None:
            target = MemoryScopeBinding(
                id=share_request.id,
                org_id=item.org_id,
                memory_id=item.memory_id,
                scope_type=share_request.to_scope_type,
                scope_id=share_request.to_scope_id,
                permission="read",
                binding_kind="shared",
                binding_status="pending",
                source_transfer_id=share_request.id,
            )
        return OrganizationGovernanceItem(
            memory_id=item.memory_id,
            memory_type=item.memory_type,
            legacy_status=item.status,
            review_status=item.review_status,
            readiness_status=item.readiness_status,
            readiness_score=float(item.promotion_score or 0),
            readiness_blockers=[str(value) for value in list(item.readiness_blockers or [])],
            summary=item.content_summary or "",
            primary_origin=self._origin_item(origins[0]) if origins else None,
            home_scope=self._scope_item(home) if home else None,
            target_scope=self._scope_item(target) if target else None,
            applicability=dict(item.applicability_json or {}),
            evidence=evidence,
            sync=MemorySyncState(
                vector_status=item.vector_status,
                graph_status=item.graph_status,
                vector_error=item.vector_error,
                graph_error=item.graph_error,
            ),
            share_request_id=str(share_request.id) if share_request else None,
            share_request_status=share_request.status if share_request else None,
            share_reason=share_request.transfer_reason if share_request else None,
            requested_by=str(share_request.requested_by or "") or None if share_request else None,
            requested_at=share_request.created_at if share_request else None,
            mapping_plan=(
                dict(share_request.mapping_plan_json)
                if share_request is not None and isinstance(getattr(share_request, "mapping_plan_json", None), dict)
                else None
            ),
            mapping_version=(
                str(getattr(share_request, "mapping_version", "") or "") or None
                if share_request is not None
                else None
            ),
            interpolation_strategy=(
                str(getattr(share_request, "interpolation_strategy", "") or "") or None
                if share_request is not None
                else None
            ),
            unmapped_fields=(
                [
                    str(value)
                    for value in list((getattr(share_request, "mapping_plan_json", None) or {}).get("unmapped_fields") or [])
                ]
                if share_request is not None and isinstance(getattr(share_request, "mapping_plan_json", None), dict)
                else []
            ),
            migration_review_required=bool(item.migration_review_required),
            migration_review_reason=item.migration_review_reason,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _dedupe_items(items: list[MemoryItem]) -> list[MemoryItem]:
        seen: set[str] = set()
        output: list[MemoryItem] = []
        for item in items:
            if item.memory_id in seen:
                continue
            seen.add(item.memory_id)
            output.append(item)
        return output

    @staticmethod
    def _origin_item(row) -> MemoryOriginItem:
        return MemoryOriginItem(
            id=str(row.id),
            origin_kind=row.origin_kind,
            source_type=row.source_type,
            source_id=row.source_id,
            trace_id=row.trace_id,
            source_span=row.source_span,
            metadata=row.metadata_json,
            occurred_at=row.occurred_at or row.created_at,
        )

    @staticmethod
    def _evidence_item(row) -> MemoryEvidenceItem:
        return MemoryEvidenceItem(
            id=str(row.id),
            evidence_role=row.evidence_role,
            source_kind=row.source_kind,
            source_type=row.source_type,
            source_id=row.source_id,
            trace_id=row.trace_id,
            task_id=row.task_id,
            rag_space_id=row.rag_space_id,
            document_id=row.document_id,
            chunk_id=row.chunk_id,
            evidence_pointer=row.evidence_pointer,
            confidence=float(row.confidence) if row.confidence is not None else None,
            weight=float(row.weight) if row.weight is not None else None,
            occurred_at=row.occurred_at or row.created_at,
        )

    @staticmethod
    def _scope_item(row) -> MemoryScopeBindingItem:
        return MemoryScopeBindingItem(
            id=str(row.id),
            scope_type=row.scope_type,
            scope_id=row.scope_id,
            permission=row.permission,
            binding_kind=row.binding_kind,
            binding_status=row.binding_status,
            approved_by=str(row.approved_by or "") or None,
            approved_at=row.approved_at,
            source_transfer_id=str(row.source_transfer_id or "") or None,
        )

    @staticmethod
    def _evidence_summary(rows: list[Any]) -> MemoryEvidenceSummary:
        return MemoryEvidenceSummary(
            origin=sum(1 for row in rows if row.evidence_role == "origin"),
            independent_support=sum(1 for row in rows if row.evidence_role == "support"),
            rag=sum(1 for row in rows if row.evidence_role == "rag"),
            agent_verification=len({row.source_id for row in rows if row.evidence_role == "agent_verification"}),
            human_confirmation=sum(1 for row in rows if row.evidence_role == "human_confirmation"),
            opposition=sum(1 for row in rows if row.evidence_role == "opposition"),
            conflict=sum(1 for row in rows if row.evidence_role == "conflict"),
            last_evidence_at=max((row.occurred_at or row.created_at for row in rows), default=None),
        )

    def _vector_payload(self, item: MemoryItem, bindings: list[MemoryScopeBinding]) -> dict[str, Any]:
        return {
            "collection": MEMORY_COLLECTION,
            "memory_id": item.memory_id,
            "org_id": self._org_id,
            "user_id": str(item.user_id or ""),
            "memory_type": item.memory_type,
            "status": "active",
            "summary": item.content_summary or "",
            "trust_score": float(item.trust_score or 0),
            "confidence": float(item.confidence or 0),
            "expires_at": item.expires_at.isoformat() if item.expires_at else "",
            "product_line": item.product_line or "",
            "rag_space_id": item.rag_space_id or "",
            "task_id": item.task_id or item.source_task_id or "",
            "extra_payload": {
                "review_status": item.review_status,
                "scope_bindings": [
                    {"scope_type": row.scope_type, "scope_id": row.scope_id}
                    for row in bindings
                ],
            },
        }
