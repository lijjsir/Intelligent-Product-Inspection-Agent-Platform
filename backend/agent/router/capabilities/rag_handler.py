from __future__ import annotations

from typing import Any

from agent.router.contracts import CapabilityContext, AgentCapabilityError


def _is_rag_overview_query(query: str) -> bool:
    text = str(query or "").strip().lower()
    if not text:
        return False
    return any(
        token in text
        for token in (
            "检测标准",
            "知识库目录",
            "目录",
            "有哪些标准",
            "有哪些文件",
            "包含什么",
            "列出",
            "overview",
        )
    )


class RagRetrieveHandler:
    """RAG retrieval capability -- standalone handler with proper error boundaries."""

    async def run(self, context: CapabilityContext):
        from agent.router.executors.base import artifact, observation

        step = context.step
        state = context.state
        request = context.request
        db_session = context.db_session

        # Handle rag.ingest
        if step.capability == "rag.ingest":
            art = artifact(
                step,
                "rag_ingest_request",
                content={
                    "requires_confirmation": True,
                    "readonly": False,
                    "message": "RAG 入库需要用户在知识库页面或确认流程中显式提交。",
                },
            )
            return observation(step, status="blocked", summary="RAG 入库需要确认", artifact_ids=[art.artifact_id]), [art]

        # RAG retrieve logic
        rag_space_id = str((state.selected_rag_space or {}).get("id") or "").strip() or None
        hits: list[dict[str, Any]] = []
        rag_space_name = str((state.selected_rag_space or {}).get("name") or "").strip()
        top_score = 0.0
        retrieval_meta: dict[str, Any] = {}
        if db_session is not None and rag_space_id:
            try:
                from app.services.rag_retrieval_service import RagRetrievalService

                service = RagRetrievalService(db_session, org_id=request.org_id, user_id=request.user_id)
                if _is_rag_overview_query(state.original_query):
                    result = await service.list_space_documents(rag_space_id=rag_space_id, limit=12)
                else:
                    result = await service.search(
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
            except Exception as exc:
                raise AgentCapabilityError(
                    code="RAG_RETRIEVE_FAILED",
                    message="知识库检索失败，无法完成当前 RAG 问答。",
                    detail={"raw_error": str(exc), "rag_space_id": rag_space_id},
                    frontend_visible=True,
                ) from exc
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
        is_empty = len(hits) == 0
        art = artifact(
            step,
            "rag_hits",
            status="empty" if is_empty else "success",
            empty_result=is_empty,
            content={
                "hit_count": len(hits),
                "top_score": top_score,
                "top_k": 5,
                "latency_ms": latency_ms,
                "candidate_count": int(retrieval_meta.get("candidate_count") or len(hits)),
                "rejected_count": int(retrieval_meta.get("rejected_count") or 0),
                "score_threshold": retrieval_meta.get("score_threshold"),
                "low_confidence_fallback": bool(retrieval_meta.get("low_confidence_fallback")),
                "overview_mode": bool(retrieval_meta.get("overview_mode")),
                "rag_space_id": rag_space_id,
                "rag_space_name": rag_space_name,
                "hits": hits,
            },
            confidence=top_score or None,
            citations=citations,
            metrics={"hit_count": len(hits), "top_score": top_score},
        )
        return (
            observation(
                step,
                status="success",
                summary=f"RAG 检索完成，命中 {len(hits)} 条" if hits else "RAG 检索成功，但没有命中相关内容。",
                artifact_ids=[art.artifact_id],
                metrics={"hit_count": len(hits), "top_score": top_score},
            ),
            [art],
        )
