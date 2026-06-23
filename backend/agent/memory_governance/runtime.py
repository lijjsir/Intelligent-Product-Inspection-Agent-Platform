from __future__ import annotations

from typing import Any


class MemoryGovernanceRuntime:
    """记忆治理运行时 — 业务 Agent 后台调用入口。

    提供两个主要入口：
    1. submit_candidate_from_artifact — 从 Agent artifact 提取候选记忆
    2. handle_contamination_event — 污染事件触发治理图
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
    ) -> dict[str, Any]:
        """从 Agent 产出中提取候选记忆并写入 MemoryService。"""
        candidate = self._extract_candidate(
            source_agent=source_agent,
            artifact=artifact,
            trace_id=trace_id,
            task_id=task_id,
        )
        if candidate is None:
            return {"status": "skipped", "reason": "no_reusable_memory"}

        try:
            from app.services.memory_service import MemoryService
            from app.schemas.memory import MemoryWriteRequest

            service = MemoryService(self.db, candidate.get("org_id", ""))
            result = await service.write_candidate(
                MemoryWriteRequest(
                    org_id=candidate.get("org_id", ""),
                    user_id=candidate.get("user_id"),
                    content=candidate.get("content", ""),
                    memory_type=candidate.get("memory_type", "candidate"),
                    source_agent=source_agent,
                    trace_id=trace_id,
                    source_task_id=task_id,
                    metadata=candidate.get("metadata") or {},
                )
            )
            return {"status": "submitted", "result": result.model_dump() if hasattr(result, "model_dump") else dict(result)}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    async def handle_contamination_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """污染事件入口 — 触发 MemoryManagerGraph 治理路径。"""
        try:
            from agent.graphs.memory_manager.graph import MemoryManagerGraph

            graph = MemoryManagerGraph().compile()
            result = await graph.ainvoke({
                "event": event,
                "org_id": event.get("org_id", ""),
                "trace_id": event.get("trace_id", ""),
                "contamination_alert": True,
            })
            return dict(result.get("final_result") or {})
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    @staticmethod
    def _extract_candidate(
        *,
        source_agent: str,
        artifact: dict[str, Any],
        trace_id: str,
        task_id: str | None = None,
    ) -> dict[str, Any] | None:
        """从 artifact 中提取候选记忆内容。"""
        answer = artifact.get("answer") or artifact.get("summary") or ""
        if not answer or len(str(answer)) < 50:
            return None

        return {
            "org_id": artifact.get("org_id", ""),
            "user_id": artifact.get("user_id"),
            "content": str(answer)[:2000],
            "memory_type": "candidate",
            "source_agent": source_agent,
            "trace_id": trace_id,
            "source_task_id": task_id,
            "metadata": {
                "confidence": artifact.get("confidence"),
                "status": artifact.get("status"),
            },
        }
