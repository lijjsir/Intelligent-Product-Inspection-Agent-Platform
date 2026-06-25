"""Service implementation of the memory.governance capability."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.api.v1.memory_helpers import build_vector_service
from app.schemas.memory import (
    EdgeType,
    MemorySearchRequest,
    RollbackAction,
)
from app.services.memory_governance_service import (
    MemoryEvaluationService,
    MemoryPropagationService,
    MemoryProvenanceService,
    MemoryRollbackService,
)
from app.services.memory_service import MemoryService


class MemoryCapabilityService:
    def __init__(self, db_session, org_id: str) -> None:
        if db_session is None:
            raise ValueError("memory.governance requires a database session")
        self._db = db_session
        self._org_id = str(org_id or "").strip()
        if not self._org_id:
            raise ValueError("memory.governance requires org_id")

    async def govern(
        self,
        *,
        task_context: dict[str, Any],
        structured_memory: list[dict[str, Any]],
        memory_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        query = str(
            task_context.get("query")
            or task_context.get("original_query")
            or ""
        ).strip()
        memory_context = await self._load_context(
            query=query,
            user_id=task_context.get("user_id"),
            trace_id=task_context.get("trace_id"),
        )
        alerts = self._detect_alerts(structured_memory, memory_events)
        propagation_nodes: list[dict[str, Any]] = []
        rollback_results: list[dict[str, Any]] = []
        evaluation_results: list[dict[str, Any]] = []

        for alert in alerts:
            memory_id = str(alert.get("memory_id") or "").strip()
            if not memory_id:
                continue
            provenance = await MemoryProvenanceService(
                self._db,
                self._org_id,
            ).trace_provenance(memory_id)
            propagation = await MemoryPropagationService(
                self._db,
                self._org_id,
            ).build_propagation_graph(
                root_memory_id=memory_id,
                max_depth=4,
                include_edge_types=[
                    EdgeType.DERIVED_FROM,
                    EdgeType.VERSION_OF,
                    EdgeType.CITED_AS_EVIDENCE,
                ],
            )
            propagation_payload = propagation.model_dump(mode="json")
            propagation_payload["provenance"] = provenance
            propagation_nodes.extend(propagation_payload.get("nodes") or [])

            actions = [
                *[
                    (target, RollbackAction.ISOLATE, "direct contamination")
                    for target in propagation.direct_contaminated
                ],
                *[
                    (target, RollbackAction.DEGRADE, "indirect contamination")
                    for target in propagation.indirect_contaminated
                ],
            ]
            for target, action, reason in actions:
                rollback = await MemoryRollbackService(
                    self._db,
                    self._org_id,
                    vector_service=build_vector_service(
                        self._org_id,
                        task_context.get("user_id"),
                        task_context.get("trace_id"),
                    ),
                ).plan_rollback(
                    root_memory_id=memory_id,
                    operator_id=self._operator_id(task_context.get("user_id")),
                    operator_role="admin",
                    trace_id=str(task_context.get("trace_id") or ""),
                    action=action,
                    target_memory_ids=[target],
                    reason=reason,
                    require_human_review=len(propagation.direct_contaminated) >= 5,
                    propagation_graph=propagation_payload,
                )
                rollback_payload = rollback.model_dump(mode="json")
                rollback_results.append(rollback_payload)
                if rollback_payload.get("affected_count"):
                    evaluation = await MemoryEvaluationService(
                        self._db,
                        self._org_id,
                    ).evaluate_recovery(
                        rollback_id=rollback.rollback_id,
                        trace_id=task_context.get("trace_id"),
                    )
                    evaluation_results.append(evaluation.model_dump(mode="json"))

        return {
            "status": "completed",
            "summary": (
                f"记忆治理完成，发现 {len(alerts)} 个污染信号，"
                f"生成 {len(rollback_results)} 个治理动作。"
            ),
            "memory_sources_used": len(memory_context),
            "contamination_nodes": len(propagation_nodes),
            "alerts": alerts,
            "rollback_results": rollback_results,
            "evaluations": evaluation_results,
        }

    async def handle_contamination_event(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.govern(
            task_context={
                "org_id": self._org_id,
                "user_id": event.get("user_id"),
                "query": event.get("query") or "",
                "trace_id": event.get("trace_id") or "",
            },
            structured_memory=list(event.get("structured_memory") or []),
            memory_events=[event],
        )

    async def _load_context(
        self,
        *,
        query: str,
        user_id: str | None,
        trace_id: str | None,
    ) -> list[dict[str, Any]]:
        if not query:
            return []
        service = MemoryService(
            self._db,
            self._org_id,
            vector_service=build_vector_service(
                self._org_id,
                user_id,
                trace_id,
            ),
        )
        response = await service.search(
            MemorySearchRequest(
                org_id=self._org_id,
                user_id=user_id,
                query=query,
                top_k=5,
                trace_id=trace_id,
            )
        )
        return [item.model_dump(mode="json") for item in response.items]

    @staticmethod
    def _detect_alerts(
        structured_memory: list[dict[str, Any]],
        memory_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for event in memory_events:
            if event.get("event_type") in {
                "memory.conflict_detected",
                "memory.write_rejected",
            }:
                alerts.append(
                    {
                        "alert_type": "conflict",
                        "memory_id": event.get("memory_id"),
                        "reason": (event.get("payload") or {}).get(
                            "reason",
                            "unknown",
                        ),
                    }
                )
        for item in structured_memory:
            trust_score = item.get("trust_score")
            if (
                trust_score is not None
                and float(trust_score) < 0.4
                and item.get("status") == "active"
            ):
                alerts.append(
                    {
                        "alert_type": "low_trust",
                        "memory_id": item.get("memory_id"),
                        "trust_score": float(trust_score),
                    }
                )
            if item.get("index_status") == "failed":
                alerts.append(
                    {
                        "alert_type": "index_failed",
                        "memory_id": item.get("memory_id"),
                        "index_error": item.get("index_error"),
                    }
                )
        return alerts

    @staticmethod
    def _operator_id(value: Any) -> str:
        try:
            return str(UUID(str(value)))
        except (TypeError, ValueError):
            return "00000000-0000-0000-0000-000000000000"
