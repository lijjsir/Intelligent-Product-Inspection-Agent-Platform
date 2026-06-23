from __future__ import annotations

from typing import Any

from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep, CapabilityContext
from agent.router.errors import AgentRuntimeError, make_agent_error
from agent.router.executors.graph_executor import GraphExecutor
from agent.router.manager_state import ManagerState


class EvidenceArbitrationExecutor(GraphExecutor):
    SUPPORTED_CAPABILITIES = {"evidence.arbitrate"}

    async def execute(
        self,
        step: AgentPlanStep,
        state: ManagerState,
        request: NormalizedRequest,
        *,
        db_session=None,
    ):
        if step.capability not in self.SUPPORTED_CAPABILITIES:
            raise make_agent_error(
                "UNSUPPORTED_CAPABILITY",
                detail={"capability": step.capability, "executor": "evidence"},
                source="evidence.executor",
            )

        # Execute via LangGraph subgraph — no silent fallback.
        # Graph failures must raise structured AgentRuntimeError.
        try:
            return await self._execute_via_graph(step, state, request, db_session)
        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise make_agent_error(
                "EVIDENCE_ARBITRATION_FAILED",
                message=f"证据仲裁图执行失败：{exc}",
                detail={
                    "step_id": step.step_id,
                    "owner_agent": step.owner_agent,
                    "capability": step.capability,
                },
                debug={
                    "raw_error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
                source="evidence.graph",
                cause=exc,
            ) from exc

    async def _execute_via_graph(self, step, state, request, db_session):
        from agent.subgraphs.evidence_arbitration import EvidenceArbitrationGraph

        graph_state = self.base_graph_state(state, request, step)
        graph_state["db_session"] = db_session
        graph_state["org_id"] = request.org_id
        graph_state["user_id"] = request.user_id
        graph_state["session_id"] = getattr(state, "session_id", None)
        graph_state["query"] = getattr(state, "original_query", "") or request.query

        result = await EvidenceArbitrationGraph().run(graph_state)

        evidence_packet = result.get("evidence_packet") or {}
        source_count = evidence_packet.get("source_count", 0)
        conflicts = evidence_packet.get("conflicts") or []
        normalized = evidence_packet.get("normalized_evidence") or []

        citations: list[dict[str, Any]] = []
        rag_items = evidence_packet.get("sources", {}).get("rag", {}).get("items", [])
        for item in rag_items:
            if isinstance(item, dict) and item.get("citations"):
                citations.extend(item["citations"])

        artifacts = self._rag_artifacts_from_graph_result(step, result)

        evidence_artifact = self._artifact(
            step,
            "evidence_packet",
            content=evidence_packet,
            citations=citations,
            metrics={
                "source_count": source_count,
                "rag_hit_count": len(rag_items),
                "memory_count": len(evidence_packet.get("sources", {}).get("memory", {}).get("items") or []),
                "kg_path_count": len(evidence_packet.get("sources", {}).get("quality_kg", {}).get("paths") or []),
                "conflict_count": len(conflicts),
                "normalized_evidence_count": len(normalized),
            },
            summary=result.get("summary", "证据仲裁完成"),
            empty_result=source_count == 0,
            status=result.get("status", "success") if source_count > 0 else "empty",
        )
        artifacts.append(evidence_artifact)

        return self._observation(
            step,
            status="success",
            summary=result.get("summary", "证据仲裁完成"),
            artifacts=artifacts,
            metrics=evidence_artifact.metrics,
        ), artifacts

    def _rag_artifacts_from_graph_result(self, step: AgentPlanStep, result: dict[str, Any]):
        artifacts = []
        rag_hits = [dict(item) for item in list(result.get("rag_hits") or []) if isinstance(item, dict)]
        if not rag_hits:
            return artifacts

        content = dict(rag_hits[-1] or {})
        hits = [dict(item) for item in list(content.get("hits") or []) if isinstance(item, dict)]
        citations = [
            {
                "id": str(item.get("chunk_id") or item.get("id") or index),
                "title": str(item.get("title") or item.get("document_name") or "RAG 片段"),
                "source": str(item.get("source") or item.get("full_path") or "rag"),
                "quote": str(item.get("quote") or item.get("text") or item.get("content") or "")[:220],
                "score": item.get("score"),
                "kind": "rag",
                "ref": f"RAG-{index}",
            }
            for index, item in enumerate(hits, start=1)
        ]
        hit_count = int(content.get("hit_count") or len(hits))
        top_score = float(content.get("top_score") or (hits[0].get("score") if hits else 0.0) or 0.0)
        artifacts.append(
            self._artifact(
                step,
                "rag_hits",
                content=content,
                citations=citations,
                confidence=top_score or None,
                metrics={"hit_count": hit_count, "top_score": top_score},
                summary=(
                    f"RAG 检索完成，命中 {hit_count} 条"
                    if hit_count
                    else "RAG 检索成功，但没有命中相关内容。"
                ),
                empty_result=hit_count == 0,
                status="success" if hit_count else "empty",
            )
        )
        return artifacts

    async def _execute_direct(self, step, state, request, db_session):
        """Fallback: direct evidence retrieval (battle-tested path)."""
        evidence_sources: dict[str, Any] = {}
        artifacts = []
        citations: list[dict[str, Any]] = []

        # RAG
        if self._rag_requested(state):
            if db_session is None:
                raise make_agent_error(
                    "RAG_RETRIEVE_FAILED",
                    message="已选择知识库，但当前请求没有可用数据库会话，无法执行 RAG 检索。",
                    detail={"selected_rag_space": state.selected_rag_space, "rag_scope": state.rag_scope},
                    source="evidence.arbitrate",
                )
            from agent.router.capabilities.rag_handler import RagRetrieveHandler

            rag_step = step.model_copy(update={"capability": "rag.retrieve", "operation": "retrieve"})
            rag_observation, rag_artifacts = await RagRetrieveHandler().run(
                CapabilityContext(
                    step=rag_step,
                    state=state,
                    request=request,
                    db_session=db_session,
                )
            )
            if rag_observation.status == "failed":
                raise make_agent_error(
                    "RAG_RETRIEVE_FAILED",
                    detail=rag_observation.error or {},
                    source="evidence.arbitrate",
                )
            artifacts.extend(rag_artifacts)
            rag_artifact = rag_artifacts[0] if rag_artifacts else None
            evidence_sources["rag"] = dict(rag_artifact.content or {}) if rag_artifact else {}
            citations.extend(list(getattr(rag_artifact, "citations", []) or []))

        # Memory
        memory_result = await self._load_memory_if_requested(state, request, db_session)
        if memory_result is not None:
            evidence_sources["memory"] = memory_result

        # KG
        kg_result = await self._load_quality_kg_if_requested(state, request)
        if kg_result is not None:
            evidence_sources["quality_kg"] = kg_result

        packet = {
            "query": state.original_query,
            "sources": evidence_sources,
            "source_count": len(evidence_sources),
            "conflicts": [],
        }
        metrics = {
            "source_count": len(evidence_sources),
            "rag_hit_count": int((evidence_sources.get("rag") or {}).get("hit_count") or 0),
            "memory_count": len((evidence_sources.get("memory") or {}).get("items") or []),
            "kg_path_count": len((evidence_sources.get("quality_kg") or {}).get("paths") or []),
        }
        evidence_artifact = self._artifact(
            step,
            "evidence_packet",
            content=packet,
            citations=citations,
            metrics=metrics,
            summary="证据仲裁完成",
            empty_result=len(evidence_sources) == 0,
            status="empty" if len(evidence_sources) == 0 else "success",
        )
        artifacts.append(evidence_artifact)
        return self._observation(
            step,
            status="success",
            summary="证据仲裁完成",
            artifacts=artifacts,
            metrics=metrics,
        ), artifacts

    @staticmethod
    def _rag_requested(state: ManagerState) -> bool:
        if bool((state.request_ext or {}).get("manager_skip_rag_evidence")):
            return False
        rag_scope = dict(state.rag_scope or {})
        return bool(state.selected_rag_space or rag_scope.get("enabled") or rag_scope.get("rag_space_id"))

    @staticmethod
    async def _load_memory_if_requested(state: ManagerState, request: NormalizedRequest, db_session) -> dict[str, Any] | None:
        scope = dict((request.ext or {}).get("memory_scope") or {})
        if not scope.get("enabled"):
            return None
        if db_session is None:
            raise make_agent_error(
                "EVIDENCE_ARBITRATION_FAILED",
                message="已启用记忆证据，但当前请求没有可用数据库会话。",
                source="evidence.arbitrate",
            )
        try:
            from app.schemas.memory import MemorySearchRequest
            from app.services.memory_service import MemoryService

            service = MemoryService(db_session, request.org_id)
            response = await service.search(
                MemorySearchRequest(
                    org_id=request.org_id,
                    user_id=request.user_id,
                    query=state.original_query,
                    top_k=int(scope.get("top_k") or 5),
                )
            )
            return {
                "items": [item.model_dump() for item in response.items],
                "trace_id": response.trace_id,
                "policy_version": response.policy_version,
            }
        except Exception as exc:
            raise make_agent_error(
                "EVIDENCE_ARBITRATION_FAILED",
                message="记忆证据检索失败。",
                debug={"raw_error": str(exc)},
                source="evidence.arbitrate",
                cause=exc,
            ) from exc

    @staticmethod
    async def _load_quality_kg_if_requested(state: ManagerState, request: NormalizedRequest) -> dict[str, Any] | None:
        kg = dict((request.ext or {}).get("quality_kg") or {})
        if not kg.get("enabled"):
            return None
        try:
            from app.services.quality_kg_service import QualityKnowledgeGraphService

            service = QualityKnowledgeGraphService(org_id=request.org_id)
            domain = str(kg.get("domain") or request.metadata.get("domain") or "通用质量检测")
            product_category = str(
                kg.get("product_category")
                or request.metadata.get("product_category")
                or request.product_id
                or ""
            )
            paths = await service.search_chain_paths_by_product(domain, product_category)
            return {"domain": domain, "product_category": product_category, "paths": paths}
        except Exception as exc:
            raise make_agent_error(
                "EVIDENCE_ARBITRATION_FAILED",
                message="质量知识图谱证据检索失败。",
                debug={"raw_error": str(exc)},
                source="evidence.arbitrate",
                cause=exc,
            ) from exc
