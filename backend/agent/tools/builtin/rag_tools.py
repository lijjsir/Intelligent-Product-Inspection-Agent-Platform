"""Built-in RAG tool manifests and lightweight handlers."""

from __future__ import annotations

from agent.tools.knowledge_search import run as knowledge_search_run


TOOL_MANIFESTS = [
    {
        "tool_key": "rag.standard_search",
        "display_name": "标准知识库检索",
        "description": "从指定 RAG 空间检索标准条款和证据片段，支持语义匹配和基础过滤。",
        "tool_type": "rag",
        "category": "RAG",
        "handler_path": "agent.tools.builtin.rag_tools.standard_search",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索查询"},
                "rag_space_id": {"type": "string", "description": "RAG 空间 ID"},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        "returns_schema": {"type": "object", "properties": {"documents": {"type": "array"}}},
        "risk_level": "low",
        "is_readonly": True,
    },
    {
        "tool_key": "rag.file_space_search",
        "display_name": "文件空间检索",
        "description": "从文件知识空间中检索相关文档片段和上下文。",
        "tool_type": "rag",
        "category": "RAG",
        "handler_path": "agent.tools.builtin.rag_tools.file_space_search",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "file_space_id": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        "returns_schema": {"type": "object", "properties": {"fragments": {"type": "array"}}},
        "risk_level": "low",
        "is_readonly": True,
    },
]


async def standard_search(query: str, rag_space_id: str | None = None, top_k: int = 5) -> dict:
    base = await knowledge_search_run(
        {
            "query": query,
            "space_id": rag_space_id,
            "top_k": top_k,
            "scope": "standard",
        }
    )
    return {
        "query": query,
        "rag_space_id": rag_space_id,
        "top_k": top_k,
        "documents": base.get("docs", []),
        "total": len(base.get("docs", [])),
    }


async def file_space_search(query: str, file_space_id: str | None = None, top_k: int = 5) -> dict:
    base = await knowledge_search_run(
        {
            "query": query,
            "space_id": file_space_id,
            "top_k": top_k,
            "scope": "file",
        }
    )
    return {
        "query": query,
        "file_space_id": file_space_id,
        "top_k": top_k,
        "fragments": base.get("docs", []),
        "total": len(base.get("docs", [])),
    }
