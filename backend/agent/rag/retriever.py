from __future__ import annotations

from typing import Any

import httpx

from agent.rag.embedder import Embedder
from app.core.config import settings


class Retriever:
    def __init__(self) -> None:
        self._embedder = Embedder()
        self._qdrant_url = settings.qdrant_url.rstrip("/")
        self._qdrant_api_key = settings.qdrant_api_key
        self._collection = settings.qdrant_collection

    async def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        vector = await self._embedder.embed(query)
        if not vector:
            return []

        payload: dict[str, Any] = {"vector": vector, "limit": top_k, "with_payload": True}
        headers: dict[str, str] = {}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{self._qdrant_url}/collections/{self._collection}/points/search",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError:
            return []

        points = data.get("result") or []
        docs: list[dict[str, Any]] = []
        for idx, point in enumerate(points):
            payload = point.get("payload") or {}
            docs.append(
                {
                    "id": str(point.get("id") or f"doc-{idx + 1}"),
                    "score": float(point.get("score") or 0.0),
                    "title": payload.get("title") or "标准文档",
                    "text": payload.get("text") or "",
                    "source": payload.get("source") or "",
                }
            )
        return docs
