from __future__ import annotations

from app.schemas.memory import (
    MemoryContext,
    MemorySearchRequest,
    RetrievalGatewayRequest,
    RetrievalGatewayResponse,
    ScopeFilter,
)
from app.services.memory_service import MemoryService
from app.services.memory_vector_service import MemoryVectorService
from app.services.rag_retrieval_service import RagRetrievalService


class RetrievalGatewayService:
    """Unified retrieval entry point for document RAG and memory RAG.

    Document RAG and memory RAG remain separate assets with separate governance
    rules. This service only coordinates retrieval and returns a unified context.
    """

    def __init__(
        self,
        session,
        *,
        org_id: str,
        user_id: str | None = None,
        memory_service: MemoryService | None = None,
        rag_service: RagRetrievalService | None = None,
    ) -> None:
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._memory_service = memory_service
        self._rag_service = rag_service

    async def search(self, request: RetrievalGatewayRequest) -> RetrievalGatewayResponse:
        warnings: list[str] = []
        degraded = False
        document_rag: dict | None = None
        document_evidence: list[dict] = []
        memory_context = None
        memory_evidence = []

        scope = request.scope

        if request.include_documents:
            if scope.rag_space_id:
                try:
                    rag_service = self._rag_service or RagRetrievalService(
                        self._session,
                        org_id=request.org_id,
                        user_id=request.user_id or self._user_id,
                    )
                    document_rag = await rag_service.search(
                        rag_space_id=scope.rag_space_id,
                        query=request.query,
                        top_k=request.top_k,
                        scope_node_ids=scope.scope_node_ids or None,
                    )
                    document_evidence = list(document_rag.get("hits") or [])
                    if document_rag.get("low_confidence_fallback"):
                        warnings.append("document_rag_low_confidence_fallback")
                except Exception:
                    degraded = True
                    warnings.append("document_rag_degraded")
            else:
                warnings.append("document_rag_skipped_no_rag_space")

        if request.include_memory:
            try:
                memory_service = self._memory_service or MemoryService(
                    self._session,
                    request.org_id,
                    vector_service=MemoryVectorService(),
                )
                memory_result = await memory_service.search(
                    MemorySearchRequest(
                        org_id=request.org_id,
                        user_id=request.user_id or self._user_id,
                        workspace=request.workspace,
                        query=request.query,
                        scope_filter=ScopeFilter(
                            memory_type=request.memory_type,
                            room_id=scope.room_id,
                            task_id=scope.task_id,
                            product_id=scope.product_id,
                            product_line=scope.product_line,
                            spec_code=scope.spec_code,
                            standard_id=scope.standard_id,
                            rag_space_id=scope.rag_space_id,
                            user_id=scope.user_id,
                            role=scope.role,
                            workspace=scope.workspace or request.workspace.value,
                            organization_id=scope.organization_id or request.org_id,
                            batch_no=scope.batch_no,
                        ),
                        top_k=request.top_k,
                    )
                )
                degraded = degraded or memory_result.degraded
                warnings.extend(memory_result.warnings)
                memory_context = memory_result.memory_context
                memory_evidence = list(memory_result.items)
            except Exception:
                degraded = True
                warnings.append("memory_rag_degraded")

        conflicts = self._detect_conflicts(
            document_evidence=document_evidence,
            memory_evidence=memory_evidence,
        )
        if conflicts:
            warnings.append("memory_document_conflict_check_required")

        return RetrievalGatewayResponse(
            query=request.query,
            document_evidence=document_evidence,
            memory_evidence=memory_evidence,
            document_rag=document_rag,
            memory_context=memory_context or MemoryContext(),
            conflicts=conflicts,
            degraded=degraded,
            warnings=list(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _detect_conflicts(
        *,
        document_evidence: list[dict],
        memory_evidence: list,
    ) -> list[dict]:
        if not document_evidence or not memory_evidence:
            return []
        conflicts: list[dict] = []
        for item in memory_evidence:
            text = " ".join(
                [
                    str(getattr(item, "summary", "") or ""),
                    " ".join(str(w) for w in getattr(item, "warnings", []) or []),
                ]
            ).lower()
            if "conflict" in text or "冲突" in text:
                conflicts.append(
                    {
                        "memory_id": getattr(item, "memory_id", ""),
                        "reason": "memory_declares_possible_conflict",
                        "document_hit_count": len(document_evidence),
                    }
                )
        return conflicts
