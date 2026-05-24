from __future__ import annotations

from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentArtifact, AgentObservation, AgentPlanStep
from agent.router.executors.base import artifact, observation
from agent.router.manager_state import ManagerState


class RagExecutor:
    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ) -> tuple[AgentObservation, list[AgentArtifact]]:
        if step.capability_key == "rag.ingest":
            art = artifact(
                "rag_ingest_request",
                "rag",
                {
                    "requires_confirmation": True,
                    "readonly": False,
                    "message": "RAG 入库需要用户在知识库页面或确认流程中显式提交。",
                },
            )
            return observation(step, status="blocked", summary="RAG 入库需要确认", artifact_ids=[art.artifact_id]), [art]

        rag_space_id = str((state.selected_rag_space or {}).get("id") or "").strip() or None
        hits: list[dict[str, Any]] = []
        rag_space_name = str((state.selected_rag_space or {}).get("name") or "").strip()
        top_score = 0.0
        retrieval_meta: dict[str, Any] = {}
        if db_session is not None and rag_space_id:
            try:
                from app.services.rag_retrieval_service import RagRetrievalService

                result = await RagRetrievalService(db_session, org_id=request.org_id, user_id=request.user_id).search(
                    rag_space_id=rag_space_id,
                    query=state.original_query,
                    top_k=5,
                    scope_node_ids=list((state.rag_scope or {}).get("scope_node_ids") or []),
                )
                retrieval_meta = dict(result)
                hits = list(result.get("hits") or [])
                rag_space_name = str(result.get("rag_space_name") or rag_space_name)
                top_score = float(hits[0].get("score") or 0.0) if hits else 0.0
                latency_ms = int(result.get("latency_ms") or 0)
            except Exception:
                hits = []
                latency_ms = 0
        else:
            latency_ms = 0
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
        art = artifact(
            "rag_hits",
            "rag",
            {
                "hit_count": len(hits),
                "top_score": top_score,
                "top_k": 5,
                "latency_ms": latency_ms,
                "candidate_count": int(retrieval_meta.get("candidate_count") or len(hits)),
                "rejected_count": int(retrieval_meta.get("rejected_count") or 0),
                "score_threshold": retrieval_meta.get("score_threshold"),
                "rag_space_id": rag_space_id,
                "rag_space_name": rag_space_name,
                "hits": hits,
            },
            confidence=top_score or None,
            citations=citations,
        )
        return (
            observation(
                step,
                status="success",
                summary="RAG 检索完成" if hits else "RAG 检索未命中或未配置知识库",
                artifact_ids=[art.artifact_id],
                metrics={"hit_count": len(hits), "top_score": top_score},
            ),
            [art],
        )
