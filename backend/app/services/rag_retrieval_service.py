from __future__ import annotations

from time import perf_counter
from typing import Any

from agent.rag.retriever import Retriever
from app.repositories.rag_space_repo import RagSpaceRepository


class RagRetrievalService:
    def __init__(self, session, *, org_id: str, user_id: str | None = None):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._spaces = RagSpaceRepository(session)
        self._retriever = Retriever(org_id=org_id)

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
                "latency_ms": 0.0,
            }

        space = await self._spaces.get(
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            owner_user_id=self._user_id,
        )
        if not space:
            return {
                "rag_space_id": rag_space_id,
                "rag_space_name": None,
                "hits": [],
                "hit_count": 0,
                "latency_ms": round((perf_counter() - started_at) * 1000, 2),
            }

        payload_filter: dict[str, Any] = {
            "org_id": self._org_id,
            "user_id": self._user_id,
            "rag_space_id": str(space.id),
        }
        if scope_node_ids:
            payload_filter["ancestor_node_ids"] = list(scope_node_ids)

        docs = await self._retriever.retrieve(
            query,
            top_k=max(int(top_k or 0), 1),
            payload_filter=payload_filter,
        )
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
            for item in docs[: max(1, top_k)]
        ]
        return {
            "rag_space_id": str(space.id),
            "rag_space_name": str(space.name),
            "hits": selected,
            "hit_count": len(selected),
            "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        }
