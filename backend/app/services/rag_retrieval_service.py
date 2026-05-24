from __future__ import annotations

from time import perf_counter
from typing import Any

from agent.rag.retriever import Retriever
from app.core.config import settings
from app.repositories.rag_space_repo import RagSpaceRepository
from infra.cache.memory_cache import _rag_result_cache, _rag_space_cache, stable_cache_key


class RagRetrievalService:
    def __init__(self, session, *, org_id: str, user_id: str | None = None):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._spaces = RagSpaceRepository(session)
        self._retriever = Retriever(org_id=org_id)

    @staticmethod
    def _score_threshold() -> float:
        try:
            return max(0.0, min(1.0, float(settings.rag_score_threshold)))
        except (TypeError, ValueError):
            return 0.55

    @classmethod
    def _is_relevant(cls, item: dict[str, Any], *, threshold: float | None = None) -> bool:
        threshold = cls._score_threshold() if threshold is None else threshold
        return float(item.get("score") or 0.0) >= threshold

    async def search(
        self,
        *,
        rag_space_id: str | None,
        query: str,
        top_k: int = 4,
        scope_node_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        started_at = perf_counter()
        if not rag_space_id:
            return {
                "rag_space_id": None,
                "rag_space_name": None,
                "hits": [],
                "hit_count": 0,
                "candidate_count": 0,
                "rejected_count": 0,
                "score_threshold": self._score_threshold(),
                "latency_ms": 0.0,
            }

        space_cache_key = f"rag_space:{self._org_id}:{self._user_id or ''}:{rag_space_id}"
        space = _rag_space_cache.get(space_cache_key)
        if space is None:
            space = await self._spaces.get(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
            )
            if space is not None:
                _rag_space_cache.set(space_cache_key, space, ttl_seconds=120)
        if not space:
            return {
                "rag_space_id": rag_space_id,
                "rag_space_name": None,
                "hits": [],
                "hit_count": 0,
                "candidate_count": 0,
                "rejected_count": 0,
                "score_threshold": self._score_threshold(),
                "latency_ms": round((perf_counter() - started_at) * 1000, 2),
            }

        payload_filter: dict[str, Any] = {
            "org_id": self._org_id,
            "user_id": self._user_id,
            "rag_space_id": str(space.id),
        }
        if scope_node_ids:
            payload_filter["ancestor_node_ids"] = list(scope_node_ids)

        normalized_query = " ".join(str(query or "").strip().lower().split())
        result_cache_key = stable_cache_key(
            "rag_result",
            self._org_id,
            self._user_id,
            str(space.id),
            sorted(scope_node_ids or []),
            normalized_query,
            max(int(top_k or 0), 1),
            self._score_threshold(),
            getattr(space, "updated_at", None),
        )
        docs = _rag_result_cache.get(result_cache_key)
        if docs is None:
            docs = await self._retriever.retrieve(
                query,
                top_k=max(int(top_k or 0), 1),
                payload_filter=payload_filter,
            )
            _rag_result_cache.set(result_cache_key, docs, ttl_seconds=120)
        score_threshold = self._score_threshold()
        candidates = docs[: max(1, top_k)]
        filtered = [item for item in candidates if self._is_relevant(item, threshold=score_threshold)]
        selected = [
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or "标准文档"),
                "source": str(item.get("full_path") or item.get("source") or item.get("title") or ""),
                "full_path": str(item.get("full_path") or item.get("source") or item.get("title") or ""),
                "quote": str(item.get("quote") or item.get("text") or "")[:220],
                "score": float(item.get("score") or 0.0),
                "chunk_index": item.get("chunk_index"),
                "page_number": item.get("page_number"),
                "document_id": item.get("document_id"),
                "node_id": item.get("node_id"),
            }
            for item in filtered
        ]
        return {
            "rag_space_id": str(space.id),
            "rag_space_name": str(space.name),
            "hits": selected,
            "hit_count": len(selected),
            "candidate_count": len(candidates),
            "rejected_count": max(0, len(candidates) - len(selected)),
            "score_threshold": score_threshold,
            "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        }

    async def search_many(
        self,
        *,
        rag_space_ids: list[str],
        query: str,
        top_k: int = 4,
        scope_node_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        started_at = perf_counter()
        unique_space_ids = [str(item).strip() for item in rag_space_ids if str(item).strip()]
        unique_space_ids = list(dict.fromkeys(unique_space_ids))
        if not unique_space_ids:
            return {
                "rag_space_id": None,
                "rag_space_name": None,
                "rag_space_ids": [],
                "rag_space_names": [],
                "hits": [],
                "hit_count": 0,
                "candidate_count": 0,
                "rejected_count": 0,
                "score_threshold": self._score_threshold(),
                "latency_ms": 0.0,
                "source_count": 0,
            }

        results = []
        for rag_space_id in unique_space_ids:
            search_kwargs = {
                "rag_space_id": rag_space_id,
                "query": query,
                "top_k": top_k,
            }
            if scope_node_ids:
                search_kwargs["scope_node_ids"] = scope_node_ids
            result = await self.search(**search_kwargs)
            for hit in list(result.get("hits") or []):
                hit["rag_space_id"] = result.get("rag_space_id")
                hit["rag_space_name"] = result.get("rag_space_name")
            results.append(result)

        all_hits: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str, str]] = set()
        rag_space_names: list[str] = []
        for result in results:
            rag_space_name = str(result.get("rag_space_name") or "").strip()
            if rag_space_name and rag_space_name not in rag_space_names:
                rag_space_names.append(rag_space_name)
            for hit in list(result.get("hits") or []):
                dedupe_key = (
                    str(hit.get("document_id") or ""),
                    str(hit.get("chunk_index") or ""),
                    str(hit.get("quote") or ""),
                )
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                all_hits.append(hit)

        all_hits.sort(
            key=lambda item: (
                -float(item.get("score") or 0.0),
                str(item.get("rag_space_name") or ""),
                str(item.get("source") or ""),
            )
        )
        selected = all_hits[: max(1, top_k)]
        hit_space_ids = []
        for item in all_hits:
            rag_space_id = str(item.get("rag_space_id") or "").strip()
            if rag_space_id and rag_space_id not in hit_space_ids:
                hit_space_ids.append(rag_space_id)
        return {
            "rag_space_id": selected[0].get("rag_space_id") if selected else None,
            "rag_space_name": selected[0].get("rag_space_name") if selected else None,
            "rag_space_ids": [str(item.get("rag_space_id") or "") for item in results if str(item.get("rag_space_id") or "").strip()],
            "rag_space_names": rag_space_names,
            "hits": selected,
            "hit_count": len(selected),
            "candidate_count": sum(int(result.get("candidate_count") or 0) for result in results),
            "rejected_count": sum(int(result.get("rejected_count") or 0) for result in results),
            "score_threshold": self._score_threshold(),
            "latency_ms": round((perf_counter() - started_at) * 1000, 2),
            "source_count": len(hit_space_ids),
        }
