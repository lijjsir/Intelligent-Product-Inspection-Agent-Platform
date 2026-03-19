from __future__ import annotations

import uuid
from typing import Any

import httpx

from agent.rag.embedder import Embedder
from app.core.config import settings


class KnowledgeIndexer:
    def __init__(self) -> None:
        self._embedder = Embedder()
        self._qdrant_url = settings.qdrant_url.rstrip("/")
        self._qdrant_api_key = settings.qdrant_api_key
        self._collection = settings.qdrant_collection

    async def ensure_collection(self, vector_size: int) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key
        payload = {"vectors": {"size": vector_size, "distance": "Cosine"}}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.put(
                f"{self._qdrant_url}/collections/{self._collection}",
                json=payload,
                headers=headers,
            )
            if resp.status_code not in (200, 201, 409):
                resp.raise_for_status()

    async def index(self, docs: list[dict[str, Any]]) -> dict[str, int]:
        points: list[dict[str, Any]] = []
        failed_embeddings = 0
        for doc in docs:
            text = str(doc.get("text") or "").strip()
            if not text:
                continue
            vector = await self._embedder.embed(text)
            if not vector:
                failed_embeddings += 1
                continue
            point_id = self._normalize_point_id(doc.get("id"))
            points.append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "title": str(doc.get("title") or "标准文档"),
                        "text": text,
                        "source": str(doc.get("source") or ""),
                    },
                }
            )

        if not points:
            return {"accepted": 0, "failed_embeddings": failed_embeddings}

        await self.ensure_collection(len(points[0]["vector"]))

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key
        payload = {"points": points}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.put(
                f"{self._qdrant_url}/collections/{self._collection}/points",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
        return {"accepted": len(points), "failed_embeddings": failed_embeddings}

    def _normalize_point_id(self, raw_id: Any) -> str | int:
        if raw_id is None:
            return str(uuid.uuid4())
        if isinstance(raw_id, int):
            return raw_id
        raw_text = str(raw_id).strip()
        if not raw_text:
            return str(uuid.uuid4())
        try:
            return str(uuid.UUID(raw_text))
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, raw_text))
