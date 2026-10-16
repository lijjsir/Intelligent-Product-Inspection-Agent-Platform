from __future__ import annotations

from time import perf_counter
from typing import Any

from agent.rag.retriever import Retriever
from app.core.config import settings
from app.repositories.rag_space_repo import RagSpaceRepository
from infra.cache.memory_cache import _rag_result_cache, _rag_space_cache, stable_cache_key


class RagRetrievalService:
    def __init__(self, session, *, org_id: str, user_id: str | None = None, include_system: bool = False):
        self._session = session
        self._org_id = org_id
        self._user_id = str(user_id).strip() if user_id is not None and str(user_id).strip() else None
        self._include_system = include_system
        self._spaces = RagSpaceRepository(session)
        self._retriever = Retriever(org_id=org_id)
        self._workspace_retriever = Retriever(org_id=org_id, collection=settings.workspace_documents_collection)

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

    def _allows_identity(self, space) -> bool:
        # Background execution without a user may read system documents only.
        # Repository owner_user_id=None means an unrestricted metadata lookup,
        # not a grant to retrieve every user's personal documents.
        if self._user_id is None:
            return self._include_system and getattr(space, "created_by", None) is None
        return True

    async def search(
        self,
        *,
        rag_space_id: str | None,
        query: str,
        top_k: int = 4,
        scope_node_ids: list[str] | None = None,
        include_low_confidence_fallback: bool = False,
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

        space_cache_key = f"rag_space:{self._org_id}:{self._user_id or ''}:{rag_space_id}" + (":system" if self._include_system else "")
        # Re-read authorization/domain; a cached space must not prolong a revoked grant.
        space = None
        if space is None:
            space = await self._spaces.get(
                org_id=self._org_id,
                rag_space_id=rag_space_id,
                owner_user_id=self._user_id,
                **({"include_system": True} if self._include_system else {}),
            )
            if space is not None:
                _rag_space_cache.set(space_cache_key, space, ttl_seconds=120)
        if not space or not self._allows_identity(space):
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

        if getattr(space, "resource_domain", None) == "formal_standard":
            from sqlalchemy import select
            from app.models.inspection_standard_library import InspectionStandardLibrary
            from app.services.standard_admission_service import StandardAdmissionService
            libraries=(await self._session.execute(select(InspectionStandardLibrary).where(
                InspectionStandardLibrary.org_id==self._org_id, InspectionStandardLibrary.deleted_at.is_(None),
                InspectionStandardLibrary.is_active.is_(True)))).scalars().all()
            ids=[lib.id for lib in libraries if str(space.id) in (lib.rag_space_ids or [])]
            result=await StandardAdmissionService(self._session,self._org_id).search({
                "query":query,"top_k":top_k,"purpose":"standard_explanation"},library_ids=ids)
            return {**result,"rag_space_id":str(space.id),"rag_space_name":space.name,
                "resource_domain":"formal_standard", "score_threshold":self._score_threshold(),"rejected_count":0}

        payload_filter: dict[str, Any] = {
            "org_id": self._org_id,
            "user_id": getattr(space, "created_by", None),
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
            bool(include_low_confidence_fallback),
            getattr(space, "updated_at", None),
        )
        docs = _rag_result_cache.get(result_cache_key)
        if docs is None:
            docs = await self._retriever.retrieve(
                query,
                top_k=max(int(top_k or 0), 1),
                payload_filter=payload_filter,
            )
            workspace_docs=await self._workspace_retriever.retrieve(query,top_k=max(int(top_k or 0),1),payload_filter=payload_filter)
            docs=sorted({str(item.get("id")):item for item in [*docs,*workspace_docs]}.values(),key=lambda item:float(item.get("score") or 0),reverse=True)
            _rag_result_cache.set(result_cache_key, docs, ttl_seconds=120)
        # A normal expert workspace is reference material only.  Older points
        # may still live in the shared legacy collection, so reject any point
        # explicitly marked as a formal standard or managed knowledge claim.
        docs = [
            item for item in docs
            if (item.get("resource_domain") or (item.get("payload") or {}).get("resource_domain"))
            not in {"formal_standard", "professional_knowledge"}
        ]
        score_threshold = self._score_threshold()
        candidates = docs[: max(1, top_k)]
        filtered = [item for item in candidates if self._is_relevant(item, threshold=score_threshold)]
        low_confidence_fallback = False
        if include_low_confidence_fallback and not filtered and candidates:
            filtered = [max(candidates, key=lambda item: float(item.get("score") or 0.0))]
            low_confidence_fallback = True
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
                "resource_domain": item.get("resource_domain") or (item.get("payload") or {}).get("resource_domain") or "workspace",
                "usage_status": "reference_only",
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
            "low_confidence_fallback": low_confidence_fallback,
            "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        }

    async def list_space_documents(self, *, rag_space_id: str, limit: int = 12) -> dict[str, Any]:
        started_at = perf_counter()
        space = await self._spaces.get(
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            owner_user_id=self._user_id,
            **({"include_system": True} if self._include_system else {}),
        )
        if not space or not self._allows_identity(space):
            return {
                "rag_space_id": rag_space_id,
                "rag_space_name": None,
                "hits": [],
                "hit_count": 0,
                "candidate_count": 0,
                "rejected_count": 0,
                "top_k": limit,
                "overview_mode": True,
                "latency_ms": round((perf_counter() - started_at) * 1000, 2),
            }

        from app.repositories.rag_space_repo import RagDocumentRepository

        docs = await RagDocumentRepository(self._session).list_for_space(
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            owner_user_id=getattr(space,"created_by",None),
            limit=limit,
            **({"include_system": True} if self._include_system else {}),
        )
        hits = [
            {
                "id": str(doc.id),
                "title": str(doc.file_name),
                "source": str(doc.file_name),
                "quote": (
                    f"{doc.file_name}，解析状态={doc.parse_status}，"
                    f"索引状态={doc.index_status}，片段数={doc.chunk_count}"
                ),
                "score": 1.0,
                "kind": "document_overview",
                "document_id": str(doc.id),
            }
            for doc in docs[: max(1, int(limit or 1))]
        ]
        return {
            "rag_space_id": str(space.id),
            "rag_space_name": str(space.name),
            "hits": hits,
            "hit_count": len(hits),
            "candidate_count": len(docs),
            "rejected_count": 0,
            "top_k": limit,
            "overview_mode": True,
            "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        }

    async def search_authorized(self, *, query: str, top_k: int = 5) -> dict[str, Any]:
        spaces = await self._spaces.list_for_org(
            org_id=self._org_id, owner_user_id=self._user_id,
            include_system=self._include_system, limit=200,
        )
        if self._user_id is None:
            spaces = [space for space in spaces if self._allows_identity(space)]
        return await self.search_many(rag_space_ids=[str(space.id) for space in spaces], query=query, top_k=top_k)

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
