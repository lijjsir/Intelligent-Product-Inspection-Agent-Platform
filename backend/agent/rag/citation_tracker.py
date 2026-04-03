from __future__ import annotations


def attach_citations(docs: list[dict]) -> list[dict]:
    """为检索文档补充统一的 citation 结构，便于结果展示和可追溯性分析。"""
    enriched: list[dict] = []
    for idx, doc in enumerate(docs, start=1):
        citation = {
            "id": doc.get("id") or f"ref-{idx}",
            "title": doc.get("title") or "标准文档",
            "source": doc.get("source") or "",
            "score": doc.get("score") or 0.0,
            "excerpt": (doc.get("text") or "")[:280],
        }
        merged = dict(doc)
        merged["citation"] = citation
        enriched.append(merged)
    return enriched
