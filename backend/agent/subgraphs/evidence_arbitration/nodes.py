from __future__ import annotations

from typing import Any


async def query_intake(state: dict[str, Any]) -> dict[str, Any]:
    request = state.get("request") or {}
    manager_state = state.get("manager_state") or {}
    ext = request.get("ext") or {}

    query = (
        state.get("query")
        or manager_state.get("original_query")
        or request.get("query")
        or ""
    )
    return {
        "query": query,
        "org_id": state.get("org_id") or request.get("org_id") or "",
        "user_id": state.get("user_id") or request.get("user_id"),
        "session_id": state.get("session_id") or request.get("session_id"),
        "workflow_run_id": state.get("workflow_run_id", ""),
        "surface": state.get("surface", "chat"),
        "request": request,
        "manager_state": manager_state,
    }


async def retrieve_rag_context(state: dict[str, Any]) -> dict[str, Any]:
    manager_state = state.get("manager_state") or {}
    rag_scope = dict(manager_state.get("rag_scope") or {})
    if not (manager_state.get("selected_rag_space") or rag_scope.get("enabled")):
        return {"rag_hits": []}

    db_session = state.get("db_session")
    if db_session is None:
        return {"rag_hits": [], "status": "rag_skipped_no_session"}

    try:
        from agent.contracts.quality_contracts import NormalizedRequest
        from agent.router.capabilities.rag_handler import RagRetrieveHandler
        from agent.router.contracts import CapabilityContext, AgentPlanStep
        from agent.router.manager_state import ManagerState

        request_data = state["request"]
        request = NormalizedRequest.model_validate(request_data)
        mgr_state = ManagerState(**{
            k: v for k, v in manager_state.items()
            if k in ManagerState.model_fields
        })
        step = AgentPlanStep(
            step_id="evidence_rag",
            owner_agent="evidence",
            capability="rag.retrieve",
            operation="retrieve",
            mode="report",
        )
        _, artifacts = await RagRetrieveHandler().run(
            CapabilityContext(
                step=step,
                state=mgr_state,
                request=request,
                db_session=db_session,
            )
        )
        rag_artifact = artifacts[0] if artifacts else None
        return {
            "rag_hits": [dict(rag_artifact.content or {})] if rag_artifact else [],
        }
    except Exception:
        return {"rag_hits": []}


async def retrieve_shared_memory_context(state: dict[str, Any]) -> dict[str, Any]:
    request = state.get("request") or {}
    ext = request.get("ext") or {}
    memory_scope = dict(ext.get("memory_scope") or {})
    if not memory_scope.get("enabled"):
        return {"shared_memory_hits": []}

    db_session = state.get("db_session")
    if db_session is None:
        return {"shared_memory_hits": []}

    try:
        from app.schemas.memory import MemorySearchRequest
        from app.services.memory_service import MemoryService

        service = MemoryService(db_session, request.get("org_id", ""))
        response = await service.search(
            MemorySearchRequest(
                org_id=request.get("org_id", ""),
                user_id=request.get("user_id"),
                query=state.get("query", ""),
                top_k=int(memory_scope.get("top_k") or 5),
            )
        )
        return {
            "shared_memory_hits": [item.model_dump() for item in response.items],
        }
    except Exception:
        return {"shared_memory_hits": []}


async def retrieve_kg_context(state: dict[str, Any]) -> dict[str, Any]:
    request = state.get("request") or {}
    ext = request.get("ext") or {}
    kg_scope = dict(ext.get("quality_kg") or {})
    if not kg_scope.get("enabled"):
        return {"kg_hits": []}

    try:
        from app.services.quality_kg_service import QualityKnowledgeGraphService

        service = QualityKnowledgeGraphService(org_id=request.get("org_id", ""))
        domain = str(kg_scope.get("domain") or request.get("metadata", {}).get("domain") or "通用质量检测")
        product_category = str(
            kg_scope.get("product_category")
            or request.get("metadata", {}).get("product_category")
            or request.get("product_id", "")
        )
        paths = await service.search_chain_paths_by_product(domain, product_category)
        return {"kg_hits": paths or []}
    except Exception:
        return {"kg_hits": []}


async def normalize_evidence(state: dict[str, Any]) -> dict[str, Any]:
    rag_hits = state.get("rag_hits") or []
    memory_hits = state.get("shared_memory_hits") or []
    kg_hits = state.get("kg_hits") or []

    evidence_items: list[dict[str, Any]] = []
    for hit in rag_hits:
        if hit:
            evidence_items.append({"source": "rag", "content": hit})
    for hit in memory_hits:
        if hit:
            evidence_items.append({"source": "memory", "content": hit})
    for hit in kg_hits:
        if hit:
            evidence_items.append({"source": "quality_kg", "content": hit})

    return {
        "normalized_evidence": evidence_items,
        "rag_hits": rag_hits,
        "shared_memory_hits": memory_hits,
        "kg_hits": kg_hits,
    }


async def llm_conflict_arbitration(state: dict[str, Any]) -> dict[str, Any]:
    evidence_items = state.get("normalized_evidence") or []
    if len(evidence_items) <= 1:
        return {"conflicts": []}

    try:
        from agent.core.llm_client import LLMClient

        evidence_texts = []
        for item in evidence_items:
            source = item.get("source", "unknown")
            content = item.get("content", {})
            evidence_texts.append(f"[{source}] {str(content)[:500]}")

        prompt = (
            "你是一个证据冲突裁决专家。请判断以下来自不同来源的证据是否存在冲突。\n\n"
            + "\n\n".join(evidence_texts)
            + "\n\n请以 JSON 格式返回：{\"conflicts\": [{\"description\": \"...\", \"sources\": [\"...\"], \"resolution\": \"...\"}]}"
        )
        result = await LLMClient.chat(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        import json
        parsed = json.loads(result)
        return {"conflicts": parsed.get("conflicts", [])}
    except Exception:
        return {"conflicts": []}


async def build_evidence_packet(state: dict[str, Any]) -> dict[str, Any]:
    evidence_sources: dict[str, Any] = {}
    if state.get("rag_hits"):
        evidence_sources["rag"] = {
            "hit_count": len(state["rag_hits"]),
            "items": state["rag_hits"],
        }
    if state.get("shared_memory_hits"):
        evidence_sources["memory"] = {
            "items": state["shared_memory_hits"],
        }
    if state.get("kg_hits"):
        evidence_sources["quality_kg"] = {
            "paths": state["kg_hits"],
        }

    source_count = len(evidence_sources)
    packet = {
        "query": state.get("query", ""),
        "sources": evidence_sources,
        "source_count": source_count,
        "conflicts": state.get("conflicts", []),
        "normalized_evidence": state.get("normalized_evidence", []),
    }

    return {
        "evidence_packet": packet,
        "status": "success" if source_count > 0 else "empty",
        "summary": f"证据检索完成，共 {source_count} 个来源",
        "confidence": 0.82,
    }
