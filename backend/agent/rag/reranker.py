from __future__ import annotations


class Reranker:
    async def rerank(self, docs: list[dict]) -> list[dict]:
        # Lightweight fallback rerank: keep high vector score and deterministic order.
        return sorted(docs, key=lambda x: float(x.get("score") or 0.0), reverse=True)
