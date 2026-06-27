from __future__ import annotations

from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep
from agent.router.errors import AgentRuntimeError, make_agent_error
from agent.router.executors.graph_executor import GraphExecutor
from agent.router.manager_state import ManagerState
from app.services.evidence_arbitration_service import EvidenceArbitrationService


class EvidenceArbitrationExecutor(GraphExecutor):
    SUPPORTED_CAPABILITIES = {"evidence.arbitrate"}

    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ):
        if step.capability not in self.SUPPORTED_CAPABILITIES:
            raise make_agent_error(
                "UNSUPPORTED_CAPABILITY",
                detail={"capability": step.capability, "executor": "orchestrator"},
                source="evidence.capability",
            )

        try:
            result = await EvidenceArbitrationService().arbitrate(
                step=step,
                state=state,
                request=request,
                db_session=db_session,
            )
        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise make_agent_error(
                "EVIDENCE_ARBITRATION_FAILED",
                message=f"证据仲裁能力执行失败：{exc}",
                detail={
                    "step_id": step.step_id,
                    "owner_agent": step.owner_agent,
                    "capability": step.capability,
                },
                debug={
                    "raw_error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
                source="evidence.capability",
                cause=exc,
            ) from exc

        evidence_packet = result.get("evidence_packet") or {}
        source_count = evidence_packet.get("source_count", 0)
        conflicts = evidence_packet.get("conflicts") or []
        normalized = evidence_packet.get("normalized_evidence") or []

        citations: list[dict[str, Any]] = []
        rag_items = evidence_packet.get("sources", {}).get("rag", {}).get("items", [])
        for item in rag_items:
            if isinstance(item, dict) and item.get("citations"):
                citations.extend(item["citations"])

        artifacts = self._rag_artifacts_from_service_result(step, result)

        evidence_artifact = self._artifact(
            step,
            "evidence_packet",
            content=evidence_packet,
            citations=citations,
            metrics={
                "source_count": source_count,
                "rag_hit_count": len(rag_items),
                "memory_count": len(evidence_packet.get("sources", {}).get("memory", {}).get("items") or []),
                "kg_path_count": len(evidence_packet.get("sources", {}).get("quality_kg", {}).get("paths") or []),
                "conflict_count": len(conflicts),
                "normalized_evidence_count": len(normalized),
            },
            summary=result.get("summary", "证据仲裁完成"),
            empty_result=source_count == 0,
            status=result.get("status", "success") if source_count > 0 else "empty",
        )
        artifacts.append(evidence_artifact)

        return self._observation(
            step,
            status="success",
            summary=result.get("summary", "证据仲裁完成"),
            artifacts=artifacts,
            metrics=evidence_artifact.metrics,
        ), artifacts

    def _rag_artifacts_from_service_result(self, step: AgentPlanStep, result: dict[str, Any]):
        artifacts = []
        rag_hits = [dict(item) for item in list(result.get("rag_hits") or []) if isinstance(item, dict)]
        if not rag_hits:
            return artifacts

        content = dict(rag_hits[-1] or {})
        hits = [dict(item) for item in list(content.get("hits") or []) if isinstance(item, dict)]
        citations = [
            {
                "id": str(item.get("chunk_id") or item.get("id") or index),
                "title": str(item.get("title") or item.get("document_name") or "RAG 片段"),
                "source": str(item.get("source") or item.get("full_path") or "rag"),
                "quote": str(item.get("quote") or item.get("text") or item.get("content") or "")[:220],
                "score": item.get("score"),
                "kind": "rag",
                "ref": f"RAG-{index}",
            }
            for index, item in enumerate(hits, start=1)
        ]
        hit_count = int(content.get("hit_count") or len(hits))
        top_score = float(content.get("top_score") or (hits[0].get("score") if hits else 0.0) or 0.0)
        artifacts.append(
            self._artifact(
                step,
                "rag_hits",
                content=content,
                citations=citations,
                confidence=top_score or None,
                metrics={"hit_count": hit_count, "top_score": top_score},
                summary=(
                    f"RAG 检索完成，命中 {hit_count} 条"
                    if hit_count
                    else "RAG 检索成功，但没有命中相关内容。"
                ),
                empty_result=hit_count == 0,
                status="success" if hit_count else "empty",
            )
        )
        return artifacts
