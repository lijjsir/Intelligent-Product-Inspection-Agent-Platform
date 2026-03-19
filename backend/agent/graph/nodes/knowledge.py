from __future__ import annotations

from datetime import datetime

from agent.graph.state import InspectionState
from agent.rag.citation_tracker import attach_citations
from agent.rag.reranker import Reranker
from agent.rag.retriever import Retriever


async def run_knowledge(state: InspectionState) -> InspectionState:
    now = datetime.utcnow().isoformat()
    query = f"产品 {state.get('product_id', '')} 检测规格 {state.get('spec_id', '')} 缺陷判定标准"
    retriever = Retriever()
    docs = await retriever.retrieve(query, top_k=5)
    docs = await Reranker().rerank(docs)
    docs = attach_citations(docs)
    state["knowledge_docs"] = docs
    state["citations"] = [d.get("citation") for d in docs if d.get("citation")]
    state.setdefault("timeline", []).append(
        {"stage": "knowledge", "message": f"RAG 召回 {len(docs)} 条标准文档", "ts": now}
    )
    return state
