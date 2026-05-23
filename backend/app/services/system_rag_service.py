from __future__ import annotations

from typing import Any

from agent.subgraphs.quality_judgement.product_adapters import detect_product_family

from app.services.inspection_standard_resolver_service import InspectionStandardResolverService
from app.services.rag_retrieval_service import RagRetrievalService


def _normalize_space_id(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _empty_rag_result() -> dict[str, Any]:
    return {
        "rag_space_id": None,
        "rag_space_name": None,
        "rag_space_ids": [],
        "rag_space_names": [],
        "hits": [],
        "hit_count": 0,
        "latency_ms": 0.0,
        "source_count": 0,
        "system_rag_space_ids": [],
        "system_rag_space_names": [],
        "standard_binding_name": None,
        "merged_rag_source_count": 0,
    }


async def resolve_and_search_system_rag(
    *,
    session,
    org_id: str,
    user_id: str | None,
    query: str,
    product_family: str | None = None,
    product_id: str | None = None,
    spec_code: str | None = None,
    user_rag_space_id: str | None = None,
    top_k: int = 4,
    scope_node_ids: list[str] | None = None,
) -> dict[str, Any]:
    binding = None
    if hasattr(session, "execute"):
        try:
            resolver = InspectionStandardResolverService(session, org_id)
            binding = await resolver.resolve(
                spec_code=spec_code,
                product_id=product_id,
                product_family=product_family,
            )
        except Exception:
            binding = None

    system_rag_space_ids = list(binding.get("system_rag_space_ids") or []) if binding else []
    merged_rag_space_ids = []
    seen_space_ids: set[str] = set()
    for candidate in [_normalize_space_id(user_rag_space_id), *[_normalize_space_id(item) for item in system_rag_space_ids]]:
        if candidate and candidate not in seen_space_ids:
            seen_space_ids.add(candidate)
            merged_rag_space_ids.append(candidate)

    if not merged_rag_space_ids:
        return _empty_rag_result()

    retrieval = RagRetrievalService(session, org_id=org_id, user_id=user_id)
    try:
        rag_result = await retrieval.search_many(
            rag_space_ids=merged_rag_space_ids,
            query=query,
            top_k=top_k,
            scope_node_ids=scope_node_ids,
        )
    except AttributeError:
        return _empty_rag_result()
    return {
        **rag_result,
        "system_rag_space_ids": system_rag_space_ids,
        "system_rag_space_names": list(binding.get("system_rag_space_names") or []) if binding else [],
        "standard_binding_name": binding.get("binding_name") if binding else None,
        "merged_rag_source_count": int(rag_result.get("source_count") or 0),
    }


def infer_product_family(
    *,
    product_family: str | None = None,
    product_id: str | None = None,
    spec_code: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    explicit = str(product_family or "").strip().lower()
    if explicit:
        return explicit
    metadata = metadata or {}
    for key in ("product_family", "category", "product_category"):
        value = str(metadata.get(key) or "").strip().lower()
        if value:
            return value
    fallback_product_id = str(product_id or metadata.get("product_id") or "").strip().lower()
    family = detect_product_family(
        {
            "product_family": metadata.get("product_family"),
            "category": metadata.get("category"),
            "product_category": metadata.get("product_category"),
            "product_id": fallback_product_id,
            "spec_code": str(spec_code or metadata.get("spec_code") or "").strip(),
        },
        fallback_product_id or None,
    )
    normalized = str(family or "").strip().lower()
    return normalized if normalized and normalized != "general" else None
