from __future__ import annotations

from typing import Any

import httpx

from agent.rag.embedder import Embedder, EmbeddingModelNotConfigured
from app.core.config import settings


class Retriever:
    def __init__(self, *, trace_id: str | None = None, task_id: str | None = None, org_id: str | None = None) -> None:
        self._embedder = Embedder(trace_id=trace_id, task_id=task_id, org_id=org_id)
        self._qdrant_url = settings.qdrant_url.rstrip("/")
        self._qdrant_api_key = settings.qdrant_api_key
        self._collection = settings.qdrant_collection

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        payload_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            vector = await self._embedder.embed(query)
        except EmbeddingModelNotConfigured:
            return []
        if not vector:
            raise RuntimeError("embedding returned empty vector")

        payload: dict[str, Any] = {"vector": vector, "limit": top_k, "with_payload": True}
        if payload_filter:
            payload["filter"] = {
                "must": [
                    {
                        "key": key,
                        "match": {"value": value},
                    }
                    for key, value in payload_filter.items()
                    if value is not None and value != ""
                ]
            }
        headers: dict[str, str] = {}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key

        try:
            async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
                response = await client.post(
                    f"{self._qdrant_url}/collections/{self._collection}/points/search",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError:
            return []

        points = data.get("result") or []
        docs: list[dict[str, Any]] = []
        for index, point in enumerate(points):
            item_payload = point.get("payload") or {}
            docs.append(
                {
                    "id": str(point.get("id") or f"doc-{index + 1}"),
                    "score": float(point.get("score") or 0.0),
                    "title": item_payload.get("title") or "标准文档",
                    "text": item_payload.get("text") or "",
                    "source": item_payload.get("source") or "",
                    "full_path": item_payload.get("full_path") or item_payload.get("source") or "",
                    "rag_space_id": item_payload.get("rag_space_id"),
                    "file_name": item_payload.get("file_name"),
                    "document_id": item_payload.get("document_id"),
                    "node_id": item_payload.get("node_id"),
                    "chunk_index": item_payload.get("chunk_index"),
                    "page_number": item_payload.get("page_number"),
                    "ancestor_node_ids": item_payload.get("ancestor_node_ids") or [],
                }
            )
        return docs
