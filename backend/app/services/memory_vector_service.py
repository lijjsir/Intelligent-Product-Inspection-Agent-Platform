"""MemoryVectorService - Qdrant indexing and semantic search for shared memory.

Uses httpx to call Qdrant REST API directly, matching the project's existing pattern.
Qdrant stores only the semantic index + payload filters; MySQL is the fact source.
"""
from __future__ import annotations

import httpx

from agent.llm.base_url_resolver import resolve_runtime_service_url
from app.core.config import settings

MEMORY_COLLECTION = "piap_shared_memory"


class MemoryVectorService:
    """Manages Qdrant vector index for shared memory semantic search."""

    def __init__(self, collection: str = MEMORY_COLLECTION) -> None:
        self._qdrant_url = resolve_runtime_service_url(
            settings.qdrant_url,
            docker_base_url=settings.qdrant_docker_url,
        )
        self._api_key = settings.qdrant_api_key
        self._collection = collection

    @property
    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["api-key"] = self._api_key
        return h

    async def ensure_collection(self, vector_size: int = 1536) -> None:
        """Create the shared memory collection if it does not exist."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Check existence
            resp = await client.get(
                f"{self._qdrant_url}/collections/{self._collection}",
                headers=self._headers,
            )
            if resp.status_code == 200:
                return

            # Create
            await client.put(
                f"{self._qdrant_url}/collections/{self._collection}",
                json={
                    "vectors": {
                        "size": vector_size,
                        "distance": "Cosine",
                    },
                },
                headers=self._headers,
            )

    async def upsert_memory(
        self,
        memory_id: str,
        org_id: str,
        user_id: str,
        workspace: str,
        memory_type: str,
        status: str,
        summary: str,
        vector: list[float] | None = None,
        trust_score: float = 0.5,
        confidence: float = 0.5,
        expires_at: str = "",
    ) -> None:
        """Upsert a memory point with payload for filtering."""
        # Generate a simple hash-based pseudo-vector if no embedding provider is wired.
        if vector is None:
            vector = self._pseudo_embed(summary)

        payload = {
            "org_id": org_id,
            "user_id": user_id,
            "workspace": workspace,
            "memory_type": memory_type,
            "status": status,
            "trust_score": trust_score,
            "confidence": confidence,
            "expires_at": expires_at,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            await client.put(
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

    async def search(
        self,
        query: str,
        org_id: str,
        workspace: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Semantic search with payload pre-filtering."""
        vector = self._pseudo_embed(query)

        qdrant_filter = {
            "must": [
                {"key": "org_id", "match": {"value": org_id}},
                {"key": "workspace", "match": {"value": workspace}},
                {"key": "status", "match": {"value": "active"}},
            ]
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
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
            except httpx.HTTPError:
                return []

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
            try:
                await client.delete(
                    f"{self._qdrant_url}/collections/{self._collection}/points",
                    json={"points": [memory_id]},
                    headers=self._headers,
                )
            except httpx.HTTPError:
                pass

    async def delete_by_org(self, org_id: str) -> None:
        """Delete all memory points for an org."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                await client.post(
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
            except httpx.HTTPError:
                pass

    @staticmethod
    def _pseudo_embed(text: str, dims: int = 256) -> list[float]:
        """Simple pseudo-embedding for use when no real embedder is wired.

        In production, replace with calls to the project's Embedder service.
        """
        import hashlib
        import math

        vec = [0.0] * dims
        words = text.lower().split()
        if not words:
            return vec

        for wi, word in enumerate(words):
            digest = hashlib.sha256(f"{wi}:{word}".encode()).digest()
            for i in range(0, len(digest), 2):
                idx = (i // 2) % dims
                val = (digest[i] * 256 + digest[i + 1]) / 65535.0
                vec[idx] += val / len(words)

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec
