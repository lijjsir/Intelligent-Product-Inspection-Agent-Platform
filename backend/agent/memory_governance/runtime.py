from __future__ import annotations

from typing import Any


class MemoryGovernanceRuntime:
    """记忆治理运行时 — 业务 Agent 后台调用入口。

    提供两个主要入口：
    1. submit_candidate_from_artifact — 从 Agent artifact 提取候选记忆
    2. handle_contamination_event — 污染事件触发治理能力
    """

    def __init__(self, db_session):
        self.db = db_session

    async def submit_candidate_from_artifact(
        self,
        *,
        source_agent: str,
        artifact: dict[str, Any],
        trace_id: str,
        task_id: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        workflow_run_id: str | None = None,
        product_line: str | None = None,
        rag_space_id: str | None = None,
        artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """从 Agent 产出中提取候选记忆并写入 MemoryService。"""
        candidate = self._extract_candidate(
            source_agent=source_agent,
            artifact=artifact,
            trace_id=trace_id,
            task_id=task_id,
            org_id=org_id,
            user_id=user_id,
            workflow_run_id=workflow_run_id,
            product_line=product_line,
            rag_space_id=rag_space_id,
            artifact_ids=artifact_ids,
        )
        if candidate is None:
            return {"status": "skipped", "reason": "no_reusable_memory"}

        try:
            from app.services.memory_service import MemoryService
            from app.api.v1.memory_helpers import build_vector_service
            from app.services.memory_vector_service import (
                CANDIDATE_MEMORY_COLLECTION,
                MEMORY_COLLECTION,
            )
            from app.schemas.memory import (
                MemoryContent,
                MemoryScope,
                MemorySource,
                MemoryType,
                MemoryWriteRequest,
            )

            service = MemoryService(
                self.db,
                candidate["org_id"],
                vector_service=build_vector_service(
                    candidate["org_id"],
                    candidate.get("user_id"),
                    trace_id,
                    collection=MEMORY_COLLECTION,
                ),
                candidate_vector_service=build_vector_service(
                    candidate["org_id"],
                    candidate.get("user_id"),
                    trace_id,
                    collection=CANDIDATE_MEMORY_COLLECTION,
                ),
            )
            result = await service.write_candidate(
                MemoryWriteRequest(
                    org_id=candidate["org_id"],
                    user_id=candidate.get("user_id"),
                    source=MemorySource(
                        kind="agent_message",
                        task_id=task_id,
                        trace_id=trace_id,
                        agent_id=source_agent,
                    ),
                    memory_type=MemoryType(candidate["memory_type"]),
                    scope=MemoryScope(**candidate["scope"]),
                    content=MemoryContent(**candidate["content"]),
                    evidence_pointers=candidate["evidence_pointers"],
                    confidence=candidate["confidence"],
                    trace_id=trace_id,
                )
            )
            return {"status": "submitted", "result": result.model_dump() if hasattr(result, "model_dump") else dict(result)}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    async def handle_contamination_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """污染事件入口 — 调用普通 Memory Capability service。"""
        try:
            from app.services.memory_capability_service import MemoryCapabilityService

            return await MemoryCapabilityService(
                self.db,
                str(event.get("org_id") or ""),
            ).handle_contamination_event(event)
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    @staticmethod
    def _extract_candidate(
        *,
        source_agent: str,
        artifact: dict[str, Any],
        trace_id: str,
        task_id: str | None = None,
        org_id: str | None = None,
        user_id: str | None = None,
        workflow_run_id: str | None = None,
        product_line: str | None = None,
        rag_space_id: str | None = None,
        artifact_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """从 artifact 中提取候选记忆内容。"""
        answer = (
            artifact.get("candidate_summary")
            or artifact.get("summary")
            or artifact.get("answer")
            or ""
        )
        confidence = float(
            artifact.get("share_value_score")
            or artifact.get("confidence")
            or artifact.get("overall_score")
            or 0.0
        )
        if not artifact.get("candidate_extractable") or not answer or confidence < 0.70:
            return None

        resolved_org_id = str(org_id or artifact.get("org_id") or "").strip()
        resolved_product_line = str(
            product_line or artifact.get("product_line") or ""
        ).strip()
        if not resolved_org_id or not resolved_product_line:
            return None

        consumed_ids = list(
            artifact_ids
            or artifact.get("consumed_artifact_ids")
            or artifact.get("evidence_used")
            or []
        )

        return {
            "org_id": resolved_org_id,
            "user_id": user_id or artifact.get("user_id"),
            "content": {
                "summary": str(answer)[:500],
                "facts": [
                    f"final_verdict: {artifact.get('final_verdict')}",
                    f"risk_level: {artifact.get('risk_level')}",
                ],
                "warnings": [
                    f"conflict: {item}"
                    for item in list(artifact.get("conflicts") or [])[:10]
                ],
                "risk_notes": [
                    str(item) for item in list(artifact.get("limitations") or [])[:10]
                ],
            },
            "memory_type": "inspection_pattern",
            "scope": {
                "task_id": task_id,
                "product_line": resolved_product_line,
                "rag_space_id": rag_space_id or artifact.get("rag_space_id"),
                "role": source_agent,
            },
            "confidence": max(0.4, min(1.0, confidence)),
            "evidence_pointers": {
                "workflow_run_id": workflow_run_id or trace_id,
                "artifact_ids": consumed_ids,
                "source": "task_blackboard",
            },
        }
