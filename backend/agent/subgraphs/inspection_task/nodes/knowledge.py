from __future__ import annotations

from agent.rag.citation_tracker import attach_citations
from agent.subgraphs.inspection_task.state import InspectionState
from app.core.datetime import utcnow_iso
from app.services.system_rag_service import resolve_and_search_system_rag
from infra.database.session import get_session


def _query_from_state(state: InspectionState) -> str:
    structured_record = state.get("structured_record") or {}
    record_excerpt = ""
    if structured_record:
        record_excerpt = str(structured_record)[:400]
    parts = [
        f"产品 {state.get('product_id', '')}",
        f"标准 {state.get('spec_code', '')}",
        f"类别 {state.get('product_family', '')}",
        "缺陷判定标准",
        record_excerpt,
    ]
    return " ".join(part.strip() for part in parts if str(part or "").strip())


async def run_knowledge(state: InspectionState) -> InspectionState:
    """基于用户 RAG 和系统标准 RAG 做合并检索，并将统一引用挂到运行态。"""
    now = utcnow_iso()
    query = _query_from_state(state)
    try:
        async with get_session() as session:
            rag_result = await resolve_and_search_system_rag(
                session=session,
                org_id=str(state.get("org_id") or ""),
                user_id=None,
                query=query,
                product_family=str(state.get("product_family") or "") or None,
                product_id=str(state.get("product_id") or "") or None,
                spec_code=str(state.get("spec_code") or "") or None,
                user_rag_space_id=str(state.get("selected_rag_space_id") or "") or None,
                top_k=5,
                scope_node_ids=list(state.get("selected_rag_scope_node_ids") or []),
            )
    except Exception as exc:
        state.setdefault("runtime_errors", []).append(
            {
                "stage": "knowledge",
                "model_id": state.get("model_id"),
                "message": str(exc),
            }
        )
        state.setdefault("timeline", []).append(
            {"stage": "knowledge", "message": f"RAG 检索失败: {exc}", "ts": now}
        )
        state["knowledge_docs"] = []
        state["citations"] = []
        state["rag_summary"] = {
            "rag_space_id": None,
            "rag_space_name": None,
            "rag_space_ids": [],
            "rag_space_names": [],
            "system_rag_space_ids": [],
            "system_rag_space_names": [],
            "standard_binding_name": None,
            "merged_rag_source_count": 0,
            "hit_count": 0,
            "top_sources": [],
            "source_graph": "inspection_task",
        }
        return state

    docs = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "source": item.get("source"),
            "full_path": item.get("full_path") or item.get("source"),
            "text": item.get("quote") or "",
            "quote": item.get("quote") or "",
            "score": float(item.get("score") or 0.0),
            "chunk_index": item.get("chunk_index"),
            "page_number": item.get("page_number"),
            "document_id": item.get("document_id"),
            "node_id": item.get("node_id"),
            "rag_space_id": item.get("rag_space_id"),
            "rag_space_name": item.get("rag_space_name"),
        }
        for item in list(rag_result.get("hits") or [])
    ]
    docs = attach_citations(docs)
    state["knowledge_docs"] = docs
    state["citations"] = [doc.get("citation") for doc in docs if doc.get("citation")]
    state["rag_summary"] = {
        "rag_space_id": rag_result.get("rag_space_id"),
        "rag_space_name": rag_result.get("rag_space_name"),
        "rag_space_ids": list(rag_result.get("rag_space_ids") or []),
        "rag_space_names": list(rag_result.get("rag_space_names") or []),
        "system_rag_space_ids": list(rag_result.get("system_rag_space_ids") or []),
        "system_rag_space_names": list(rag_result.get("system_rag_space_names") or []),
        "standard_binding_name": rag_result.get("standard_binding_name"),
        "merged_rag_source_count": int(rag_result.get("merged_rag_source_count") or 0),
        "hit_count": int(rag_result.get("hit_count") or 0),
        "top_sources": list(dict.fromkeys(str(item.get("source") or "") for item in docs if str(item.get("source") or "").strip()))[:5],
        "source_graph": "inspection_task",
    }
    state.setdefault("timeline", []).append(
        {
            "stage": "knowledge",
            "message": (
                f"RAG 合并检索完成，命中 {len(docs)} 条证据，"
                f"来源数 {state['rag_summary']['merged_rag_source_count']}"
            ),
            "ts": now,
        }
    )
    return state
