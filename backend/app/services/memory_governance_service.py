"""MemoryGovernanceService - provenance, propagation, rollback, evaluation.

Coordinates the governance closed loop:
  contamination alert -> provenance -> propagation graph -> rollback -> recovery evaluation
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.ids import uuid7
from app.models.approval import Approval
from app.models.memory import MemoryDependencyEdge, MemoryEvaluation, MemoryItem, MemoryRollback
from app.repositories.approval_repo import ApprovalRepository
from app.repositories.memory_repo import (
    MemoryDependencyRepository,
    MemoryEvaluationRepository,
    MemoryEventRepository,
    MemoryItemRepository,
    MemoryPolicyRepository,
    MemoryRollbackRepository,
)
from app.schemas.memory import (
    EdgeType,
    MemoryEvaluationResponse,
    MemoryPropagationResponse,
    MemoryRollbackResponse,
    MemoryStatus,
    PropagationNode,
    ReviewStatus,
    RollbackAction,
)
from app.services.memory_vector_service import MemoryVectorService


class MemoryProvenanceService:
    """Reconstructs source event chain for a given memory."""

    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id
        self._item_repo = MemoryItemRepository(session, org_id)
        self._event_repo = MemoryEventRepository(session, org_id)
        self._dep_repo = MemoryDependencyRepository(session, org_id)

    async def trace_provenance(self, memory_id: str, trace_id: str | None = None) -> dict:
        """Reconstruct the source chain: events, evidence pointers, write subject, version parent."""
        memory = await self._item_repo.get_by_memory_id(memory_id)
        if not memory:
            return {"error": "memory not found", "memory_id": memory_id}

        events = await self._event_repo.list_by_org(
            memory_id=memory_id,
            trace_id=trace_id or memory.trace_id,
            limit=200,
        )

        edges = await self._dep_repo.list_by_target(memory_id)

        return {
            "memory_id": memory_id,
            "source_events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "source_kind": e.source_kind,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ],
            "evidence_pointers": memory.evidence_pointers,
            "created_by_type": memory.created_by_type,
            "version_parent_id": memory.version_parent_id,
            "trace_id": memory.trace_id,
            "upstream_edges": [
                {
                    "source_memory_id": e.source_memory_id,
                    "edge_type": e.edge_type,
                    "strength": float(e.strength) if e.strength else None,
                }
                for e in edges
            ],
        }


class MemoryPropagationService:
    """Builds contamination propagation subgraph from dependency edges."""

    # Only provenance edges participate in default contamination propagation.
    # Semantic edges and audit edges do NOT propagate contamination.
    PROPAGATION_EDGE_TYPES = [
        EdgeType.VERSION_OF.value,
        EdgeType.SUMMARIZED_FROM.value,
        EdgeType.MERGED_FROM.value,
        EdgeType.DERIVED_FROM.value,
        EdgeType.CITED_AS_EVIDENCE.value,
        EdgeType.PLANNED_FROM.value,
        EdgeType.ROLLBACK_DEPENDS_ON.value,
    ]

    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id
        self._dep_repo = MemoryDependencyRepository(session, org_id)
        self._item_repo = MemoryItemRepository(session, org_id)

    async def build_propagation_graph(
        self,
        root_memory_id: str,
        max_depth: int = 4,
        include_edge_types: list[EdgeType] | None = None,
    ) -> MemoryPropagationResponse:
        edge_types = [e.value for e in include_edge_types] if include_edge_types else self.PROPAGATION_EDGE_TYPES
        visited: dict[str, PropagationNode] = {}
        direct: list[str] = []
        indirect: list[str] = []
        suspected: list[str] = []
        clean: list[str] = []

        await self._bfs(root_memory_id, edge_types, max_depth, visited)

        for node in visited.values():
            if node.classification == "direct_contaminated":
                direct.append(node.memory_id)
            elif node.classification == "indirect_contaminated":
                indirect.append(node.memory_id)
            elif node.classification == "suspected":
                suspected.append(node.memory_id)
            else:
                clean.append(node.memory_id)

        return MemoryPropagationResponse(
            root_memory_id=root_memory_id,
            nodes=list(visited.values()),
            direct_contaminated=direct,
            indirect_contaminated=indirect,
            suspected=suspected,
            clean_boundary=clean,
        )

    async def _bfs(
        self,
        root: str,
        edge_types: list[str],
        max_depth: int,
        visited: dict[str, PropagationNode],
    ) -> None:
        from collections import deque

        queue = deque([(root, 0, None, None)])
        visited[root] = PropagationNode(
            memory_id=root,
            classification="direct_contaminated",
            depth=0,
            affected_by=[],
        )

        while queue:
            current, depth, parent_edge, parent_id = queue.popleft()
            if depth >= max_depth:
                continue

            # Find downstream memories that depend on the contaminated node
            edges = await self._dep_repo.list_by_target(current)
            for edge in edges:
                if edge.edge_type not in edge_types:
                    continue
                downstream = edge.source_memory_id  # the memory that depends on current
                if downstream in visited:
                    if parent_id and parent_id not in visited[downstream].affected_by:
                        visited[downstream].affected_by.append(parent_id)
                    continue

                # Classify
                if depth == 0:
                    classification = "indirect_contaminated"
                elif edge.strength and float(edge.strength) < 0.3:
                    classification = "suspected"
                elif depth >= max_depth - 1:
                    classification = "clean_boundary"
                else:
                    classification = "indirect_contaminated"

                node = PropagationNode(
                    memory_id=downstream,
                    classification=classification,
                    depth=depth + 1,
                    edge_type=edge.edge_type,
                    affected_by=[current],
                )
                visited[downstream] = node
                queue.append((downstream, depth + 1, edge.edge_type, current))


class MemoryRollbackService:
    """Executes rollback actions and coordinates side effects."""

    def __init__(self, session, org_id: str, vector_service: MemoryVectorService | None = None):
        self._session = session
        self._org_id = org_id
        self._item_repo = MemoryItemRepository(session, org_id)
        self._event_repo = MemoryEventRepository(session, org_id)
        self._rollback_repo = MemoryRollbackRepository(session, org_id)
        self._dep_repo = MemoryDependencyRepository(session, org_id)
        self._approval_repo = ApprovalRepository(session)
        self._vector = vector_service

    async def plan_rollback(
        self,
        root_memory_id: str,
        operator_id: str,
        operator_role: str,
        trace_id: str,
        action: RollbackAction,
        target_memory_ids: list[str],
        reason: str,
        require_human_review: bool = False,
        propagation_graph: dict | None = None,
    ) -> MemoryRollbackResponse:
        """Phase 1: Create rollback plan and approval. Does NOT execute if review required."""
        if action == RollbackAction.BRANCH:
            raise ValueError("BRANCH rollback is not supported")

        rollback_id = f"rb_{uuid.uuid4().hex[:12]}"

        if require_human_review:
            rollback_record = MemoryRollback(
                id=str(uuid7()),
                org_id=self._org_id,
                rollback_id=rollback_id,
                root_memory_id=root_memory_id,
                operator_id=operator_id,
                rollback_action=action.value,
                target_memory_ids=target_memory_ids,
                propagation_graph_json=propagation_graph,
                reason=reason,
                require_human_review=True,
                review_status=ReviewStatus.PENDING.value,
                trace_id=trace_id,
            )
            await self._rollback_repo.create(rollback_record)

            approval_id = await self._create_followup_approval(
                rollback_id=rollback_id,
                root_memory_id=root_memory_id,
                operator_id=operator_id,
                operator_role=operator_role,
                action=action,
                target_memory_ids=target_memory_ids,
                reason=reason,
                propagation_graph=propagation_graph,
                affected_count=len(target_memory_ids),
                require_human_review=True,
            )

            return MemoryRollbackResponse(
                rollback_id=rollback_id,
                root_memory_id=root_memory_id,
                action=action,
                affected_count=0,
                review_status=ReviewStatus.PENDING,
                approval_id=approval_id,
            )

        rollback_record = MemoryRollback(
            id=str(uuid7()),
            org_id=self._org_id,
            rollback_id=rollback_id,
            root_memory_id=root_memory_id,
            operator_id=operator_id,
            rollback_action=action.value,
            target_memory_ids=target_memory_ids,
            propagation_graph_json=propagation_graph,
            reason=reason,
            require_human_review=False,
            review_status=ReviewStatus.NOT_REQUIRED.value,
            trace_id=trace_id,
            execution_status="planned",
        )
        await self._rollback_repo.create(rollback_record)

        # No review needed — execute immediately
        return await self._apply_rollback(
            rollback_id=rollback_id,
            root_memory_id=root_memory_id,
            operator_id=operator_id,
            trace_id=trace_id,
            action=action,
            target_memory_ids=target_memory_ids,
            reason=reason,
            propagation_graph=propagation_graph,
            final_review_status=ReviewStatus.NOT_REQUIRED,
        )

    async def apply_rollback(self, rollback_id: str) -> MemoryRollbackResponse:
        """Phase 2: Execute a previously planned rollback after approval."""
        rollback_record = await self._rollback_repo.get_by_rollback_id(rollback_id)
        if not rollback_record:
            raise ValueError(f"Rollback {rollback_id} not found")
        if rollback_record.review_status != ReviewStatus.PENDING.value:
            raise ValueError(f"Rollback {rollback_id} is not in pending state")

        return await self._apply_rollback(
            rollback_id=rollback_id,
            root_memory_id=rollback_record.root_memory_id,
            operator_id=rollback_record.operator_id,
            trace_id=rollback_record.trace_id or "",
            action=RollbackAction(rollback_record.rollback_action),
            target_memory_ids=list(rollback_record.target_memory_ids or []),
            reason=rollback_record.reason or "",
            propagation_graph=rollback_record.propagation_graph_json,
        )

    async def _apply_rollback(
        self,
        rollback_id: str,
        root_memory_id: str,
        operator_id: str,
        trace_id: str,
        action: RollbackAction,
        target_memory_ids: list[str],
        reason: str,
        propagation_graph: dict | None = None,
        final_review_status: ReviewStatus = ReviewStatus.APPROVED,
    ) -> MemoryRollbackResponse:
        """Internal: execute the actual rollback actions."""
        if action == RollbackAction.BRANCH:
            raise ValueError("BRANCH rollback is not supported")

        try:
            before_snapshot = await self._snapshot(target_memory_ids)

            affected = 0
            for mid in target_memory_ids:
                memory = await self._item_repo.get_by_memory_id(mid)
                if not memory:
                    continue

                if action == RollbackAction.DELETE:
                    await self._item_repo.update_status(mid, MemoryStatus.DELETED.value)
                    if self._vector:
                        await self._vector.delete_memory(mid)
                    await self._dep_repo.soft_delete_by_memory(mid)
                    affected += 1

                elif action == RollbackAction.DEGRADE:
                    new_score = (float(memory.trust_score) if memory.trust_score else 0.5) * 0.5
                    await self._item_repo.update_trust_score(mid, new_score)
                    affected += 1

                elif action == RollbackAction.ISOLATE:
                    await self._item_repo.update_status(mid, MemoryStatus.ISOLATED.value)
                    if self._vector:
                        await self._vector.delete_memory(mid)
                    affected += 1

                elif action == RollbackAction.PATCH:
                    await self._apply_patch(mid, propagation_graph=propagation_graph, trace_id=trace_id)
                    affected += 1

            after_snapshot = await self._snapshot(target_memory_ids)

            await self._rollback_repo.update_review_status(rollback_id, final_review_status.value)
            await self._rollback_repo.update_execution_status(rollback_id, "applied")

            from app.models.memory import MemoryEvent
            event = MemoryEvent(
                id=str(uuid7()),
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                org_id=self._org_id,
                event_type="memory.rollback_applied",
                trace_id=trace_id,
                memory_id=root_memory_id,
                payload_json={
                    "rollback_id": rollback_id,
                    "action": action.value,
                    "targets": target_memory_ids,
                    "reason": reason,
                },
            )
            await self._event_repo.create(event)

            return MemoryRollbackResponse(
                rollback_id=rollback_id,
                root_memory_id=root_memory_id,
                action=action,
                affected_count=affected,
                review_status=final_review_status,
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot,
            )
        except Exception as exc:
            await self._rollback_repo.update_execution_status(rollback_id, "failed", str(exc))
            raise

    async def _apply_patch(
        self,
        memory_id: str,
        *,
        propagation_graph: dict | None = None,
        trace_id: str | None = None,
    ) -> str:
        """Apply PATCH by isolating the old memory and creating a replacement version."""
        old_item = await self._item_repo.get_by_memory_id(memory_id)
        if not old_item:
            raise ValueError(f"Memory {memory_id} not found")

        patch_payload = dict((propagation_graph or {}).get("patch") or {})
        content_summary = str(patch_payload.get("content_summary") or "").strip()
        if not content_summary:
            raise ValueError("PATCH rollback requires propagation_graph.patch.content_summary")
        content_json = patch_payload.get("content_json")
        if content_json is None:
            content_json = dict(old_item.content_json or {})

        await self._item_repo.update_status(memory_id, MemoryStatus.ISOLATED.value)
        if self._vector:
            await self._vector.delete_memory(memory_id)

        new_memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        replacement = MemoryItem(
            id=str(uuid7()),
            memory_id=new_memory_id,
            org_id=self._org_id,
            user_id=old_item.user_id,
            memory_type=old_item.memory_type,
            scope_json=old_item.scope_json,
            content_summary=content_summary,
            content_json=content_json,
            source_event_ids=old_item.source_event_ids,
            evidence_pointers=old_item.evidence_pointers,
            version_parent_id=memory_id,
            trust_score=old_item.trust_score,
            confidence=old_item.confidence,
            usage_policy=old_item.usage_policy,
            ttl_policy=old_item.ttl_policy,
            privacy_level=old_item.privacy_level,
            status=MemoryStatus.ACTIVE.value,
            rollback_policy=getattr(old_item, "rollback_policy", None),
            created_by=getattr(old_item, "created_by", None),
            created_by_type=getattr(old_item, "created_by_type", None),
            trace_id=trace_id or old_item.trace_id,
            expires_at=old_item.expires_at,
            source_trace_id=getattr(old_item, "source_trace_id", None) or old_item.trace_id,
            source_task_id=getattr(old_item, "source_task_id", None),
            index_status="pending",
            index_error=None,
            policy_key=getattr(old_item, "policy_key", None),
            policy_version=getattr(old_item, "policy_version", None),
            last_accessed_at=datetime.now(timezone.utc),
            access_count=0,
        )
        await self._item_repo.create(replacement)
        await self._dep_repo.upsert_edge(
            source_memory_id=new_memory_id,
            target_memory_id=memory_id,
            edge_type=EdgeType.VERSION_OF.value,
            strength=1.0,
            metadata_json={
                "edge_group": "provenance",
                "relation_source": "rollback_patch",
                "reason": "patch replacement version",
                "observed_count": 1,
                "last_observed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        if self._vector:
            await self._vector.upsert_memory(
                memory_id=new_memory_id,
                org_id=self._org_id,
                user_id=str(old_item.user_id or ""),
                memory_type=old_item.memory_type,
                status=MemoryStatus.ACTIVE.value,
                summary=content_summary,
                trust_score=float(old_item.trust_score or 0),
                confidence=float(old_item.confidence or 0),
            )
        return new_memory_id

    async def _snapshot(self, memory_ids: list[str]) -> dict:
        snapshot: dict[str, Any] = {}
        for mid in memory_ids:
            mem = await self._item_repo.get_by_memory_id(mid)
            if mem:
                snapshot[mid] = {
                    "status": mem.status,
                    "trust_score": float(mem.trust_score) if getattr(mem, "trust_score", None) is not None else None,
                    "confidence": float(mem.confidence) if getattr(mem, "confidence", None) is not None else None,
                }
        return snapshot

    def _should_create_followup_approval(
        self,
        action: RollbackAction,
        target_memory_ids: list[str],
        require_human_review: bool,
    ) -> bool:
        if require_human_review:
            return True
        if action in {RollbackAction.DELETE, RollbackAction.PATCH}:
            return True
        return len(target_memory_ids) >= 5

    def _resolve_risk_level(
        self,
        action: RollbackAction,
        target_memory_ids: list[str],
        require_human_review: bool,
    ) -> str:
        if require_human_review or len(target_memory_ids) >= 10:
            return "critical"
        if action in {RollbackAction.DELETE, RollbackAction.PATCH} or len(target_memory_ids) >= 5:
            return "high"
        return "medium"

    async def _create_followup_approval(
        self,
        rollback_id: str,
        root_memory_id: str,
        operator_id: str,
        operator_role: str,
        action: RollbackAction,
        target_memory_ids: list[str],
        reason: str,
        propagation_graph: dict | None,
        affected_count: int,
        require_human_review: bool,
    ) -> str | None:
        if not self._should_create_followup_approval(action, target_memory_ids, require_human_review):
            return None

        approval = Approval(
            id=str(uuid7()),
            org_id=self._org_id,
            source_module="memory_governance",
            source_id=rollback_id,
            operation_summary=f"记忆回滚复核: {action.value} root={root_memory_id} affected={affected_count}",
            risk_level=self._resolve_risk_level(action, target_memory_ids, require_human_review),
            payload_json={
                "rollback_id": rollback_id,
                "root_memory_id": root_memory_id,
                "action": action.value,
                "target_memory_ids": target_memory_ids,
                "affected_count": affected_count,
                "reason": reason,
                "propagation_graph_summary": propagation_graph,
                "require_human_review": require_human_review,
            },
            requester_id=operator_id,
            requester_role=operator_role,
            status="pending",
        )
        await self._approval_repo.create(approval)
        return approval.id


class MemoryEvaluationService:
    """Post-rollback recovery verification."""

    def __init__(self, session, org_id: str):
        self._session = session
        self._org_id = org_id
        self._eval_repo = MemoryEvaluationRepository(session, org_id)
        self._rollback_repo = MemoryRollbackRepository(session, org_id)
        self._item_repo = MemoryItemRepository(session, org_id)

    async def evaluate_recovery(
        self,
        rollback_id: str,
        task_id: str | None = None,
        trace_id: str | None = None,
        scenario: str | None = None,
    ) -> MemoryEvaluationResponse:
        evaluation_id = f"eval_{uuid.uuid4().hex[:12]}"

        rollback = await self._rollback_repo.get_by_rollback_id(rollback_id)
        if not rollback:
            return MemoryEvaluationResponse(
                evaluation_id=evaluation_id,
                rollback_id=rollback_id,
                conclusion="rollback not found",
            )

        # Compute basic metrics
        metrics = await self._compute_metrics(rollback)

        evaluation = MemoryEvaluation(
            id=str(uuid7()),
            org_id=self._org_id,
            evaluation_id=evaluation_id,
            rollback_id=rollback_id,
            task_id=task_id,
            trace_id=trace_id,
            scenario=scenario,
            metrics_json=metrics,
            conclusion=metrics.get("summary", ""),
        )
        await self._eval_repo.create(evaluation)

        return MemoryEvaluationResponse(
            evaluation_id=evaluation_id,
            rollback_id=rollback_id,
            scenario=scenario,
            metrics=metrics,
            conclusion=metrics.get("summary"),
        )

    async def _compute_metrics(self, rollback: MemoryRollback) -> dict:
        target_ids = rollback.target_memory_ids or []
        affected = len(target_ids)

        # Check how many are now properly isolated/deleted
        isolated_count = 0
        for mid in target_ids:
            mem = await self._item_repo.get_by_memory_id(mid)
            if mem and mem.status in ("deleted", "isolated", "disabled"):
                isolated_count += 1

        return {
            "affected_memories": affected,
            "properly_contained": isolated_count,
            "containment_rate": isolated_count / affected if affected > 0 else 0.0,
            "action": rollback.rollback_action,
            "review_status": rollback.review_status,
            "summary": (
                f"Rollback {rollback.rollback_id}: {isolated_count}/{affected} "
                f"memories properly contained via {rollback.rollback_action}"
            ),
        }
