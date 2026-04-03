from __future__ import annotations


class Reranker:
    async def rerank(self, docs: list[dict]) -> list[dict]:
        """按现有向量分数做轻量重排，作为没有专用 reranker 时的兜底实现。"""
        # Lightweight fallback rerank: keep high vector score and deterministic order.
        return sorted(docs, key=lambda x: float(x.get("score") or 0.0), reverse=True)
