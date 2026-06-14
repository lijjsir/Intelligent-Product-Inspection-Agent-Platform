"""MemoryVectorService - Qdrant indexing and semantic search for shared memory.

Uses httpx to call Qdrant REST API directly, matching the project's existing pattern.
Qdrant stores only the semantic index + payload filters; MySQL is the fact source.
"""
from __future__ import annotations

import httpx
import uuid
from typing import Callable, Awaitable

from agent.llm.base_url_resolver import resolve_runtime_service_url
from app.core.config import settings

MEMORY_COLLECTION = "piap_shared_memory"
CANDIDATE_MEMORY_COLLECTION = "piap_candidate_memory"

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

    @staticmethod
    def _point_id(memory_id: str) -> str:
        """Qdrant point IDs must be UUIDs or unsigned integers."""
        raw = str(memory_id or "").strip()
        try:
            return str(uuid.UUID(raw))
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, f"piap-memory:{raw}"))

    async def ensure_collection(self, vector_size: int = 1536) -> None:
        """Create the shared memory collection if it does not exist."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{self._qdrant_url}/collections/{self._collection}",
                headers=self._headers,
            )
            if resp.status_code == 200:
                return
            if resp.status_code != 404:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise MemoryVectorServiceError(
                        f"Qdrant collection check failed: {exc.response.text}"
                    ) from exc

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
            try:
                create_resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MemoryVectorServiceError(
                    f"Qdrant collection create failed: {exc.response.text}"
                ) from exc

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
        extra_payload: dict | None = None,
    ) -> None:
        """Upsert a memory point with payload for filtering."""
        if vector is None:
            vector = await self._embed(summary)

        await self.ensure_collection(vector_size=len(vector))

        payload = {
            "memory_id": memory_id,
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
        if extra_payload:
            payload.update(extra_payload)

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
            except httpx.HTTPStatusError as exc:
                raise MemoryVectorServiceError(
                    f"Qdrant memory upsert failed: {exc.response.text}"
                ) from exc

    async def search(
        self,
        query: str = "",
        org_id: str = "",
        top_k: int = 5,
        *,
        status: str = "active",
        user_id: str | None = None,
        memory_types: list[str] | None = None,
        product_line: str | None = None,
        rag_space_id: str | None = None,
        task_id: str | None = None,
        vector: list[float] | None = None,
        filter_conditions: dict | None = None,
    ) -> list[dict]:
        """Semantic search with payload pre-filtering. Raises on failure.

        When *vector* is provided it is used directly (no embedding call).
        When *filter_conditions* is provided it replaces the built filter
        (org_id, status, user_id, memory_types, etc. are ignored).
        """
        if vector is None:
            vector = await self._embed(query)

        if filter_conditions is not None:
            qdrant_filter = filter_conditions
        else:
            must_clauses: list[dict] = [
                {"key": "org_id", "match": {"value": org_id}},
                {"key": "status", "match": {"value": status}},
            ]

            if memory_types:
                if len(memory_types) == 1:
                    must_clauses.append({"key": "memory_type", "match": {"value": memory_types[0]}})
                else:
                    must_clauses.append({"key": "memory_type", "match": {"any": memory_types}})

            if product_line:
                must_clauses.append({"key": "product_line", "match": {"value": product_line}})

            if rag_space_id:
                must_clauses.append({"key": "rag_space_id", "match": {"value": rag_space_id}})

            if task_id:
                must_clauses.append({"key": "task_id", "match": {"value": task_id}})

            qdrant_filter = {"must": must_clauses}
            if user_id:
                user_conditions = [
                    {"key": "user_id", "match": {"value": user_id}},
                    {"key": "user_id", "match": {"value": ""}},
                ]
                qdrant_filter["should"] = user_conditions
                qdrant_filter["min_should"] = {
                    "conditions": user_conditions,
                    "min_count": 1,
                }

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
            if resp.status_code == 404:
                await self.ensure_collection(vector_size=len(vector))
                return []
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MemoryVectorServiceError(
                    f"Qdrant memory search failed: {exc.response.text}"
                ) from exc
            data = resp.json()

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
            resp = await client.delete(
                f"{self._qdrant_url}/collections/{self._collection}/points",
                json={"points": [self._point_id(memory_id)]},
                headers=self._headers,
            )
            if resp.status_code == 404:
                return
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MemoryVectorServiceError(
                    f"Qdrant memory delete failed: {exc.response.text}"
                ) from exc

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
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MemoryVectorServiceError(
                    f"Qdrant org memory delete failed: {exc.response.text}"
                ) from exc
