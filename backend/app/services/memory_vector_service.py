"""MemoryVectorService - Qdrant indexing and semantic search for shared memory.

Uses httpx to call Qdrant REST API directly, matching the project's existing pattern.
Qdrant stores only the semantic index + payload filters; MySQL is the fact source.
"""
from __future__ import annotations

import httpx
from typing import Callable, Awaitable

from agent.llm.base_url_resolver import resolve_runtime_service_url
from app.core.config import settings

MEMORY_COLLECTION = "piap_shared_memory"

EmbedderFactory = Callable[..., Awaitable[list[float]]]


class MemoryVectorServiceError(RuntimeError):
    """Raised when Qdrant vector operations fail."""


class MemoryVectorService:
    """Manages Qdrant vector index for shared memory semantic search."""

    def __init__(
        self,
        collection: str = MEMORY_COLLECTION,
        embedder_factory: EmbedderFactory | None = None,
        *,
        org_id: str = "",
        user_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self._qdrant_url = resolve_runtime_service_url(
            settings.qdrant_url,
            docker_base_url=settings.qdrant_docker_url,
        )
        self._api_key = settings.qdrant_api_key
        self._collection = collection
        self._embedder_factory = embedder_factory
        self._org_id = org_id
        self._user_id = user_id
        self._trace_id = trace_id

    @property
    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["api-key"] = self._api_key
        return h

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding via the real Embedder. No pseudo-embedding fallback."""
        if self._embedder_factory is None:
            raise MemoryVectorServiceError(
                "MemoryVectorService: no embedder_factory configured"
            )
        try:
            return await self._embedder_factory(text)
        except Exception as exc:
            raise MemoryVectorServiceError(
                f"Embedding generation failed: {exc}"
            ) from exc

    async def ensure_collection(self, vector_size: int = 1536) -> None:
        """Create the shared memory collection if it does not exist."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{self._qdrant_url}/collections/{self._collection}",
                headers=self._headers,
            )
            if resp.status_code == 200:
                return

            create_resp = await client.put(
                f"{self._qdrant_url}/collections/{self._collection}",
                json={
                    "vectors": {
                        "size": vector_size,
                        "distance": "Cosine",
                    },
                },
                headers=self._headers,
            )
            create_resp.raise_for_status()

    async def upsert_memory(
        self,
        memory_id: str,
        org_id: str,
        user_id: str,
        memory_type: str,
        status: str,
        summary: str,
        vector: list[float] | None = None,
        trust_score: float = 0.5,
        confidence: float = 0.5,
        expires_at: str = "",
        product_line: str = "",
        rag_space_id: str = "",
        task_id: str = "",
    ) -> None:
        """Upsert a memory point with payload for filtering."""
        if vector is None:
            vector = await self._embed(summary)

        payload = {
            "org_id": org_id,
            "user_id": user_id,
            "memory_type": memory_type,
            "status": status,
            "trust_score": trust_score,
            "confidence": confidence,
            "expires_at": expires_at,
            "product_line": product_line,
            "rag_space_id": rag_space_id,
            "task_id": task_id,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.put(
                f"{self._qdrant_url}/collections/{self._collection}/points",
                json={
                    "points": [
                        {
                            "id": memory_id,
                            "vector": vector,
                            "payload": payload,
                        }
                    ]
                },
                headers=self._headers,
            )
            resp.raise_for_status()

    async def search(
        self,
        query: str,
        org_id: str,
        top_k: int = 5,
        *,
        user_id: str | None = None,
        memory_types: list[str] | None = None,
        product_line: str | None = None,
        rag_space_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict]:
        """Semantic search with payload pre-filtering. Raises on failure."""
        vector = await self._embed(query)

        must_clauses: list[dict] = [
            {"key": "org_id", "match": {"value": org_id}},
            {"key": "status", "match": {"value": "active"}},
        ]

        if user_id:
            must_clauses.append({"key": "user_id", "match": {"value": user_id}})

        if memory_types:
            should_clauses = [
                {"key": "memory_type", "match": {"value": mt}} for mt in memory_types
            ]
            must_clauses.append({"should": should_clauses})

        if product_line:
            must_clauses.append({"key": "product_line", "match": {"value": product_line}})

        if rag_space_id:
            must_clauses.append({"key": "rag_space_id", "match": {"value": rag_space_id}})

        if task_id:
            must_clauses.append({"key": "task_id", "match": {"value": task_id}})

        qdrant_filter = {"must": must_clauses}

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{self._qdrant_url}/collections/{self._collection}/points/search",
                json={
                    "vector": vector,
                    "limit": top_k,
                    "with_payload": True,
                    "filter": qdrant_filter,
                },
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[dict] = []
        for point in data.get("result", []):
            results.append({
                "memory_id": point.get("id"),
                "score": point.get("score", 0.0),
                "payload": point.get("payload", {}),
            })
        return results

    async def delete_memory(self, memory_id: str) -> None:
        """Remove a memory vector point."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.delete(
                f"{self._qdrant_url}/collections/{self._collection}/points",
                json={"points": [memory_id]},
                headers=self._headers,
            )
            resp.raise_for_status()

    async def delete_by_org(self, org_id: str) -> None:
        """Delete all memory points for an org."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{self._qdrant_url}/collections/{self._collection}/points/delete",
                json={
                    "filter": {
                        "must": [
                            {"key": "org_id", "match": {"value": org_id}}
                        ]
                    }
                },
                headers=self._headers,
            )
            resp.raise_for_status()
