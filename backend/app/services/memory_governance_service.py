"""MemoryGovernanceService - provenance, propagation, rollback, evaluation.

Coordinates the governance closed loop:
  contamination alert -> provenance -> propagation graph -> rollback -> recovery evaluation
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.ids import uuid7
from app.models.memory import MemoryEvaluation, MemoryRollback
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

    EDGE_TYPES_FORWARD = [
        "derived_from", "read_by", "used_as_tool_param",
        "cited_as_evidence", "version_of", "merged_from",
        "summarized_from", "planned_from",
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
        edge_types = [e.value for e in include_edge_types] if include_edge_types else self.EDGE_TYPES_FORWARD
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

            edges = await self._dep_repo.list_by_source(current)
            for edge in edges:
                if edge.edge_type not in edge_types:
                    continue
                target = edge.target_memory_id
                if target in visited:
                    # Append additional parent
                    if parent_id and parent_id not in visited[target].affected_by:
                        visited[target].affected_by.append(parent_id)
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
                    memory_id=target,
                    classification=classification,
                    depth=depth + 1,
                    edge_type=edge.edge_type,
                    affected_by=[current],
                )
                visited[target] = node
                queue.append((target, depth + 1, edge.edge_type, current))


class MemoryRollbackService:
    """Executes rollback actions and coordinates side effects."""

    def __init__(self, session, org_id: str, vector_service: MemoryVectorService | None = None):
        self._session = session
        self._org_id = org_id
        self._item_repo = MemoryItemRepository(session, org_id)
        self._event_repo = MemoryEventRepository(session, org_id)
        self._rollback_repo = MemoryRollbackRepository(session, org_id)
        self._dep_repo = MemoryDependencyRepository(session, org_id)
        self._vector = vector_service

    async def execute_rollback(
        self,
        root_memory_id: str,
        operator_id: str,
        workspace: str,
        trace_id: str,
        action: RollbackAction,
        target_memory_ids: list[str],
        reason: str,
        require_human_review: bool = False,
        propagation_graph: dict | None = None,
    ) -> MemoryRollbackResponse:
        rollback_id = f"rb_{uuid.uuid4().hex[:12]}"

        # Snapshot before
        before_snapshot = await self._snapshot(target_memory_ids)

        # Apply action
        affected = 0
        for mid in target_memory_ids:
            memory = await self._item_repo.get_by_memory_id(mid)
            if not memory:
                continue

            if action == RollbackAction.DELETE:
                await self._item_repo.update_status(mid, MemoryStatus.DELETED.value)
                if self._vector:
                    try:
                        await self._vector.delete_memory(mid)
                    except Exception:
                        pass
                await self._dep_repo.soft_delete_by_memory(mid)
                affected += 1

            elif action == RollbackAction.DEGRADE:
                new_score = (float(memory.trust_score) if memory.trust_score else 0.5) * 0.5
                await self._item_repo.update_trust_score(mid, new_score)
                affected += 1

            elif action == RollbackAction.ISOLATE:
                await self._item_repo.update_status(mid, MemoryStatus.ISOLATED.value)
                if self._vector:
                    try:
                        await self._vector.delete_memory(mid)
                    except Exception:
                        pass
                affected += 1

            elif action == RollbackAction.PATCH:
                # Soft-delete original and expect a new version via write_candidate
                await self._item_repo.soft_delete(mid)
                affected += 1

            elif action == RollbackAction.BRANCH:
                await self._item_repo.update_status(mid, MemoryStatus.ISOLATED.value)
                affected += 1

        # Snapshot after
        after_snapshot = await self._snapshot(target_memory_ids)

        review_status = (
            ReviewStatus.PENDING if require_human_review else ReviewStatus.NOT_REQUIRED
        )

        rollback_record = MemoryRollback(
            id=str(uuid7()),
            org_id=self._org_id,
            rollback_id=rollback_id,
            root_memory_id=root_memory_id,
            operator_id=operator_id,
            workspace=workspace,
            rollback_action=action.value,
            target_memory_ids=target_memory_ids,
            propagation_graph_json=propagation_graph,
            before_snapshot_json=before_snapshot,
            after_snapshot_json=after_snapshot,
            reason=reason,
            require_human_review=require_human_review,
            review_status=review_status.value,
            trace_id=trace_id,
        )
        await self._rollback_repo.create(rollback_record)

        # Record event
        from app.models.memory import MemoryEvent
        event = MemoryEvent(
            id=str(uuid7()),
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            org_id=self._org_id,
            workspace=workspace,
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
            review_status=review_status,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )

    async def _snapshot(self, memory_ids: list[str]) -> dict:
        snapshot: dict[str, Any] = {}
        for mid in memory_ids:
            mem = await self._item_repo.get_by_memory_id(mid)
            if mem:
                snapshot[mid] = {
                    "status": mem.status,
                    "trust_score": float(mem.trust_score) if mem.trust_score else None,
                    "confidence": float(mem.confidence) if mem.confidence else None,
                }
        return snapshot


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
