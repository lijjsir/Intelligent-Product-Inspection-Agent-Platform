from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.rag_retrieval_service import RagRetrievalService
from infra.database.session import get_session


class RagScope(BaseModel):
    """统一 RAG 检索范围定义。两个 Agent 都使用此模型。"""
    enabled: bool = False
    rag_space_id: str | None = None
    scope_node_ids: list[str] = Field(default_factory=list)
    scope_mode: Literal["space", "subtree", "files"] = "space"
    top_k: int = 8


class RagContext:
    """RAG 检索上下文结果"""
    query: str = ""
    hits: list[dict[str, Any]] = Field(default_factory=list)
    hit_count: int = 0
    rag_space_id: str | None = None
    rag_space_name: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    citation_coverage: float = 0.0
    source_graph: str = ""
    degraded: bool = False
    degrade_reason: str | None = None


class RagContextBuilder:
    """统一的 RAG 上下文构建器。

    两个 Agent (QualityChatAgent / InspectionTaskAgent) 都通过此服务进行 RAG 检索，
    避免各自写一套 RAG 逻辑。
    """

    @staticmethod
    def normalize_scope(ext: dict[str, Any]) -> RagScope:
        """从请求 ext 中提取并规范化 RAG 范围"""
        scope_data = ext.get("rag_scope") or {}
        if isinstance(scope_data, dict):
            return RagScope(
                enabled=bool(scope_data.get("enabled") or ext.get("selected_rag_space_id")),
                rag_space_id=str(scope_data.get("rag_space_id") or ext.get("selected_rag_space_id") or "") or None,
                scope_node_ids=list(scope_data.get("scope_node_ids") or ext.get("selected_rag_scope_node_ids") or []),
                scope_mode=str(scope_data.get("scope_mode") or "space"),
                top_k=int(scope_data.get("top_k") or 8),
            )
        # Fallback: construct from legacy ext fields
        return RagScope(
            enabled=bool(ext.get("selected_rag_space_id")),
            rag_space_id=str(ext.get("selected_rag_space_id") or "") or None,
            scope_node_ids=list(ext.get("selected_rag_scope_node_ids") or []),
            top_k=8,
        )

    @staticmethod
    def build_retrieval_query(*, user_query: str, product_id: str = "",
                              spec_code: str = "", context_parts: list[str] | None = None) -> str:
        """构建统一的 RAG 检索查询字符串"""
        parts = [user_query]
        if product_id:
            parts.append(product_id)
        if spec_code:
            parts.append(spec_code)
        if context_parts:
            parts.extend(context_parts)
        return " ".join(part.strip() for part in parts if str(part or "").strip())

    async def retrieve(
        self,
        *,
        org_id: str,
        user_id: str,
        query: str,
        scope: RagScope,
        source_graph: str = "rag_context_builder",
    ) -> RagContext:
        """执行 RAG 检索并返回上下文"""
        ctx = RagContext(query=query, source_graph=source_graph)

        if not scope.enabled or not scope.rag_space_id:
            ctx.degraded = True
            ctx.degrade_reason = "RAG scope not enabled or no space selected"
            return ctx

        try:
            async with get_session() as session:
                service = RagRetrievalService(session, org_id=org_id, user_id=user_id)
                result = await service.search(
                    rag_space_id=scope.rag_space_id,
                    query=query,
                    top_k=scope.top_k,
                    scope_node_ids=scope.scope_node_ids,
                )
        except Exception as exc:
            ctx.degraded = True
            ctx.degrade_reason = f"RAG retrieval failed: {str(exc)}"
            return ctx

        hits = list(result.get("hits") or [])
        ctx.hits = hits
        ctx.hit_count = int(result.get("hit_count") or len(hits))
        ctx.rag_space_id = str(result.get("rag_space_id") or scope.rag_space_id)
        ctx.rag_space_name = str(result.get("rag_space_name") or "")

        if not hits and scope.enabled:
            ctx.degraded = True
            ctx.degrade_reason = "当前知识库未找到足够依据"

        return ctx

    @staticmethod
    def build_citations(hits: list[dict[str, Any]], *, prefix: str = "rag") -> list[dict[str, Any]]:
        """将 RAG 检索命中转换为引用格式"""
        citations = []
        for index, hit in enumerate(hits, start=1):
            citations.append({
                "id": f"{prefix}-{index}",
                "title": str(hit.get("title") or f"RAG 引用 {index}"),
                "source": str(hit.get("source") or ""),
                "quote": str(hit.get("quote") or ""),
                "score": float(hit.get("score") or 0.0),
                "kind": "rag",
            })
        return citations

    @staticmethod
    def build_prompt_context(hits: list[dict[str, Any]], *, max_chars: int = 4000) -> str:
        """将 RAG 检索命中转换为 LLM prompt 上下文"""
        parts: list[str] = []
        total = 0
        for hit in hits:
            title = str(hit.get("title") or "Untitled")
            quote = str(hit.get("quote") or "")
            source = str(hit.get("source") or "")
            chunk = f"[{title}] ({source})\n{quote}\n"
            if total + len(chunk) > max_chars:
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n".join(parts)
