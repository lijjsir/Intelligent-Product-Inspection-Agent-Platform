from __future__ import annotations

from datetime import datetime

from agent.graph.state import InspectionState
from agent.rag.citation_tracker import attach_citations
from agent.rag.reranker import Reranker
from agent.rag.retriever import Retriever


async def run_knowledge(state: InspectionState) -> InspectionState:
    """检索并重排检测标准证据，再为后续推理阶段挂载引用信息。"""
    now = datetime.utcnow().isoformat()
    query = f"产品 {state.get('product_id', '')} 检测标准 {state.get('spec_code', '')} 缺陷判定标准"
    retriever = Retriever(
        trace_id=state.get("trace_id"),
        task_id=state.get("task_id"),
        org_id=state.get("org_id"),
    )
    try:
        docs = await retriever.retrieve(query, top_k=5)
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
        return state

    docs = await Reranker().rerank(docs)
    docs = attach_citations(docs)
    state["knowledge_docs"] = docs
    state["citations"] = [d.get("citation") for d in docs if d.get("citation")]
    state.setdefault("timeline", []).append(
        {"stage": "knowledge", "message": f"RAG 召回 {len(docs)} 条标准文档", "ts": now}
    )
    return state
