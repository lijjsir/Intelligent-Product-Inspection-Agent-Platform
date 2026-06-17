"""MemoryVectorService - Qdrant indexing and semantic search for shared memory.

Uses httpx to call Qdrant REST API directly, matching the project's existing pattern.
Qdrant stores only the semantic index + payload filters; MySQL is the fact source.
"""
from __future__ import annotations

import uuid

import httpx

from agent.llm.base_url_resolver import resolve_runtime_service_url
from agent.rag.embedder import Embedder
from app.core.config import settings

MEMORY_COLLECTION = "piap_shared_memory"
MEMORY_POINT_NAMESPACE = uuid.UUID("1cc6d080-ecf5-4eb7-9eda-bf7d6f111111")


class MemoryVectorError(RuntimeError):
    pass


class MemoryVectorService:
    """Manages Qdrant vector index for shared memory semantic search."""

    def __init__(
        self,
        collection: str = MEMORY_COLLECTION,
        embedder: Embedder | None = None,
    ) -> None:
        self._qdrant_url = resolve_runtime_service_url(
            settings.qdrant_url,
            docker_base_url=settings.qdrant_docker_url,
        )
        self._api_key = settings.qdrant_api_key
        self._collection = collection
        self._embedder = embedder

    @property
    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["api-key"] = self._api_key
        return h

    @staticmethod
    def _point_id(memory_id: str) -> str:
        return str(uuid.uuid5(MEMORY_POINT_NAMESPACE, str(memory_id)))

    async def _embed(self, text: str) -> list[float]:
        embedder = self._embedder or Embedder(allow_pseudo_fallback=False)
        vector = await embedder.embed(text)
        if not vector:
            raise MemoryVectorError("embedding returned empty vector")
        return vector

    async def ensure_collection(self, vector_size: int) -> None:
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
            resp = await client.put(
                f"{self._qdrant_url}/collections/{self._collection}",
                json={
                    "vectors": {
                        "size": vector_size,
                        "distance": "Cosine",
                    },
                },
                headers=self._headers,
            )
            try:
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise MemoryVectorError(f"qdrant collection create failed: {exc}") from exc

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
        scope_type: str | None = None,
        scope_id: str | None = None,
        scope_payload: dict | None = None,
        trust_score: float = 0.5,
        confidence: float = 0.5,
        expires_at: str = "",
    ) -> None:
        """Upsert a memory point with payload for filtering."""
        if vector is None:
            vector = await self._embed(summary)
        await self.ensure_collection(len(vector))

        payload = {
            "memory_id": memory_id,
            "org_id": org_id,
            "user_id": user_id,
            "workspace": workspace,
            "memory_type": memory_type,
            "status": status,
            "scope_type": scope_type or "",
            "scope_id": scope_id or "",
            "scope": scope_payload or {},
            "trust_score": trust_score,
            "confidence": confidence,
            "expires_at": expires_at,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.put(
                f"{self._qdrant_url}/collections/{self._collection}/points",
                json={
                    "points": [
                        {
                            "id": self._point_id(memory_id),
                            "vector": vector,
                            "payload": payload,
                        }
                    ]
                },
                headers=self._headers,
            )
            try:
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise MemoryVectorError(f"qdrant memory upsert failed: {exc}") from exc

    async def search(
        self,
        query: str,
        org_id: str,
        workspace: str,
        top_k: int = 5,
        scope_filters: list[dict[str, str]] | None = None,
        memory_types: list[str] | None = None,
    ) -> list[dict]:
        """Semantic search with payload pre-filtering."""
        vector = await self._embed(query)

        qdrant_filter = {
            "must": [
                {"key": "org_id", "match": {"value": org_id}},
                {"key": "workspace", "match": {"value": workspace}},
                {"key": "status", "match": {"value": "active"}},
            ]
        }
        if memory_types:
            qdrant_filter["must"].append(
                {"key": "memory_type", "match": {"any": list(memory_types)}}
            )
        if scope_filters:
            should = []
            for scope_filter in scope_filters:
                scope_type = str(scope_filter.get("scope_type") or "").strip()
                scope_id = str(scope_filter.get("scope_id") or "").strip()
                if scope_type and scope_id:
                    should.append(
                        {
                            "must": [
                                {"key": "scope_type", "match": {"value": scope_type}},
                                {"key": "scope_id", "match": {"value": scope_id}},
                            ]
                        }
                    )
                elif scope_type:
                    should.append({"key": "scope_type", "match": {"value": scope_type}})
            if should:
                qdrant_filter["should"] = should

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
            except httpx.HTTPError as exc:
                raise MemoryVectorError(f"qdrant memory search failed: {exc}") from exc

        results: list[dict] = []
        for point in data.get("result", []):
            payload = point.get("payload", {}) or {}
            results.append({
                "memory_id": payload.get("memory_id") or point.get("id"),
                "score": point.get("score", 0.0),
                "payload": payload,
            })
        return results

    async def delete_memory(self, memory_id: str) -> None:
        """Remove a memory vector point."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.post(
                    f"{self._qdrant_url}/collections/{self._collection}/points/delete",
                    json={"points": [self._point_id(memory_id)]},
                    headers=self._headers,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise MemoryVectorError(f"qdrant memory delete failed: {exc}") from exc

    async def delete_by_org(self, org_id: str) -> None:
        """Delete all memory points for an org."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
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
            except httpx.HTTPError as exc:
                raise MemoryVectorError(f"qdrant org memory delete failed: {exc}") from exc
