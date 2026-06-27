"""Fixed evidence retrieval and arbitration workflow.

Evidence arbitration is an orchestrator capability, not a business Agent and
does not require a LangGraph wrapper.
"""
from __future__ import annotations

import json
from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep, CapabilityContext
from agent.router.errors import AgentRuntimeError, make_agent_error
from agent.router.manager_state import ManagerState


class EvidenceArbitrationService:
    async def arbitrate(
        self,
        *,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        db_session=None,
    ) -> dict[str, Any]:
        query = state.original_query or request.query
        rag_hits = await self._retrieve_rag(
            step=step,
            state=state,
            request=request,
            db_session=db_session,
        )
        memory_hits = await self._retrieve_shared_memory(
            state=state,
            request=request,
            db_session=db_session,
        )
        kg_hits = await self._retrieve_quality_kg(state=state, request=request)
        normalized = self._normalize(rag_hits, memory_hits, kg_hits)
        conflicts = await self._arbitrate_conflicts(
            state=state,
            evidence_items=normalized,
        )
        return self._build_result(
            query=query,
            rag_hits=rag_hits,
            memory_hits=memory_hits,
            kg_hits=kg_hits,
            normalized=normalized,
            conflicts=conflicts,
        )

    async def _retrieve_rag(
        self,
        *,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        db_session,
    ) -> list[dict[str, Any]]:
        rag_scope = dict(state.rag_scope or {})
        if (state.request_ext or {}).get("manager_skip_rag_evidence") is True:
            return []
        if state.surface == "quality_task":
            if db_session is None:
                raise make_agent_error(
                    "RAG_RETRIEVE_FAILED",
                    message="正式质检任务需要检索真实标准证据，但当前请求没有数据库会话。",
                    source="evidence.arbitrate",
                )
            return await self._retrieve_quality_task_rag(
                state=state,
                request=request,
                db_session=db_session,
            )
        if not (state.selected_rag_space or rag_scope.get("enabled")):
            return []
        if db_session is None:
            raise make_agent_error(
                "RAG_RETRIEVE_FAILED",
                message="已启用 RAG 证据检索，但当前请求没有数据库会话。",
                source="evidence.arbitrate",
            )

        from agent.router.capabilities.rag_handler import RagRetrieveHandler

        rag_step = step.model_copy(
            update={
                "owner_agent": "orchestrator",
                "capability": "rag.retrieve",
                "operation": "retrieve",
            }
        )
        _observation, artifacts = await RagRetrieveHandler().run(
            CapabilityContext(
                step=rag_step,
                state=state,
                request=request,
                db_session=db_session,
            )
        )
        artifact = artifacts[0] if artifacts else None
        return [dict(artifact.content or {})] if artifact else []

    async def _retrieve_quality_task_rag(
        self,
        *,
        state: ManagerState,
        request: NormalizedRequest,
        db_session,
    ) -> list[dict[str, Any]]:
        metadata = dict(request.metadata or {})
        ext = dict(request.ext or {})
        rag_scope = dict(ext.get("rag_scope") or state.rag_scope or {})
        structured_record = (
            metadata.get("structured_record")
            if isinstance(metadata.get("structured_record"), dict)
            else {}
        )
        product_id = str(
            request.product_id
            or metadata.get("product_id")
            or structured_record.get("product_id")
            or ""
        ).strip()
        spec_code = str(
            request.spec_code
            or metadata.get("spec_code")
            or structured_record.get("spec_code")
            or ""
        ).strip()
        product_family = str(
            metadata.get("product_family")
            or structured_record.get("product_family")
            or product_id
            or ""
        ).strip() or None
        user_rag_space_id = str(
            rag_scope.get("rag_space_id")
            or metadata.get("selected_rag_space_id")
            or ""
        ).strip() or None
        query = " ".join(
            value
            for value in (
                f"产品 {product_id}" if product_id else "",
                f"标准 {spec_code}" if spec_code else "",
                f"类别 {product_family}" if product_family else "",
                "缺陷判定标准",
                str(structured_record)[:400] if structured_record else "",
            )
            if value
        )

        try:
            from app.services.system_rag_service import resolve_and_search_system_rag

            result = await resolve_and_search_system_rag(
                session=db_session,
                org_id=request.org_id,
                user_id=request.user_id,
                query=query,
                product_family=product_family,
                product_id=product_id or None,
                spec_code=spec_code or None,
                user_rag_space_id=user_rag_space_id,
                top_k=5,
                scope_node_ids=list(rag_scope.get("scope_node_ids") or []),
            )
        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise make_agent_error(
                "RAG_RETRIEVE_FAILED",
                message="正式质检任务 RAG 证据检索失败。",
                debug={
                    "raw_error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
                source="evidence.arbitrate",
                cause=exc,
            ) from exc

        hits = list(result.get("hits") or [])
        return [
            {
                "hit_count": int(result.get("hit_count") or len(hits)),
                "top_score": float(hits[0].get("score") or 0.0) if hits else 0.0,
                "top_k": 5,
                "latency_ms": int(float(result.get("latency_ms") or 0)),
                "candidate_count": int(result.get("candidate_count") or len(hits)),
                "rejected_count": int(result.get("rejected_count") or 0),
                "score_threshold": result.get("score_threshold"),
                "rag_space_id": result.get("rag_space_id") or user_rag_space_id,
                "rag_space_name": result.get("rag_space_name"),
                "rag_space_ids": list(result.get("rag_space_ids") or []),
                "rag_space_names": list(result.get("rag_space_names") or []),
                "system_rag_space_ids": list(
                    result.get("system_rag_space_ids") or []
                ),
                "system_rag_space_names": list(
                    result.get("system_rag_space_names") or []
                ),
                "standard_binding_name": result.get("standard_binding_name"),
                "merged_rag_source_count": int(
                    result.get("merged_rag_source_count") or 0
                ),
                "hits": hits,
            }
        ]

    async def _retrieve_shared_memory(
        self,
        *,
        state: ManagerState,
        request: NormalizedRequest,
        db_session,
    ) -> list[dict[str, Any]]:
        scope = dict((request.ext or {}).get("memory_scope") or {})
        if not scope.get("enabled"):
            return []
        if db_session is None:
            raise make_agent_error(
                "EVIDENCE_ARBITRATION_FAILED",
                message="已启用共享记忆证据，但当前请求没有数据库会话。",
                source="evidence.arbitrate",
            )
        try:
            from app.api.v1.memory_helpers import build_vector_service
            from app.schemas.memory import MemorySearchRequest
            from app.services.memory_service import MemoryService

            service = MemoryService(
                db_session,
                request.org_id,
                vector_service=build_vector_service(
                    request.org_id,
                    request.user_id,
                    state.trace_id or state.workflow_run_id,
                ),
            )
            response = await service.search(
                MemorySearchRequest(
                    org_id=request.org_id,
                    user_id=request.user_id,
                    query=state.original_query,
                    top_k=int(scope.get("top_k") or 5),
                )
            )
            return [item.model_dump() for item in response.items]
        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise make_agent_error(
                "EVIDENCE_ARBITRATION_FAILED",
                message="共享记忆证据检索失败。",
                debug={
                    "raw_error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
                source="evidence.arbitrate",
                cause=exc,
            ) from exc

    @staticmethod
    async def _retrieve_quality_kg(
        *,
        state: ManagerState,
        request: NormalizedRequest,
    ) -> list[dict[str, Any]]:
        scope = dict((request.ext or {}).get("quality_kg") or {})
        if not scope.get("enabled"):
            return []
        try:
            from app.services.quality_kg_service import QualityKnowledgeGraphService

            service = QualityKnowledgeGraphService(org_id=request.org_id)
            domain = str(
                scope.get("domain")
                or request.metadata.get("domain")
                or "通用质量检测"
            )
            product_category = str(
                scope.get("product_category")
                or request.metadata.get("product_category")
                or request.product_id
                or ""
            )
            return list(
                await service.search_chain_paths_by_product(
                    domain,
                    product_category,
                )
                or []
            )
        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise make_agent_error(
                "EVIDENCE_ARBITRATION_FAILED",
                message="质量知识图谱证据检索失败。",
                debug={
                    "raw_error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
                source="evidence.arbitrate",
                cause=exc,
            ) from exc

    @staticmethod
    def _normalize(
        rag_hits: list[dict[str, Any]],
        memory_hits: list[dict[str, Any]],
        kg_hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            *[
                {"source": "rag", "content": item}
                for item in rag_hits
                if item
            ],
            *[
                {"source": "memory", "content": item}
                for item in memory_hits
                if item
            ],
            *[
                {"source": "quality_kg", "content": item}
                for item in kg_hits
                if item
            ],
        ]

    @staticmethod
    async def _arbitrate_conflicts(
        *,
        state: ManagerState,
        evidence_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(evidence_items) <= 1:
            return []
        from agent.subgraphs.common.llm_runtime import run_llm_chat

        evidence_text = "\n\n".join(
            f"[{item.get('source', 'unknown')}] "
            f"{str(item.get('content') or {})[:500]}"
            for item in evidence_items
        )
        content, _llm_meta = await run_llm_chat(
            state={
                "org_id": state.org_id,
                "user_id": state.user_id,
                "workflow_run_id": state.workflow_run_id,
                "manager_model_runtime": state.manager_model_runtime,
            },
            messages=[
                {
                    "role": "user",
                    "content": (
                        "判断以下证据是否冲突，仅返回 JSON："
                        '{"conflicts":[{"description":"","sources":[],"resolution":""}]}\n'
                        f"{evidence_text}"
                    ),
                }
            ],
            temperature=0.1,
            observation_name="evidence.conflict_arbitration",
            source="evidence.arbitrate",
        )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise make_agent_error(
                "EVIDENCE_ARBITRATION_FAILED",
                message="证据冲突裁决模型未返回合法 JSON。",
                debug={"raw_error": str(exc), "model_output": content[:500]},
                source="evidence.arbitrate",
                cause=exc,
            ) from exc
        return [
            dict(item)
            for item in list(parsed.get("conflicts") or [])
            if isinstance(item, dict)
        ]

    @staticmethod
    def _build_result(
        *,
        query: str,
        rag_hits: list[dict[str, Any]],
        memory_hits: list[dict[str, Any]],
        kg_hits: list[dict[str, Any]],
        normalized: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sources: dict[str, Any] = {}
        if rag_hits:
            sources["rag"] = {"hit_count": len(rag_hits), "items": rag_hits}
        if memory_hits:
            sources["memory"] = {"items": memory_hits}
        if kg_hits:
            sources["quality_kg"] = {"paths": kg_hits}
        first_rag = rag_hits[0] if rag_hits else {}
        packet = {
            "query": query,
            "sources": sources,
            "source_count": len(sources),
            "conflicts": conflicts,
            "normalized_evidence": normalized,
            "rag_space_id": first_rag.get("rag_space_id"),
            "rag_space_name": first_rag.get("rag_space_name"),
            "top_k": int(first_rag.get("top_k") or 0),
        }
        return {
            "evidence_packet": packet,
            "rag_hits": rag_hits,
            "status": "success" if sources else "empty",
            "summary": f"证据检索完成，共 {len(sources)} 个来源",
            "confidence": 0.82 if sources else 0.0,
        }
