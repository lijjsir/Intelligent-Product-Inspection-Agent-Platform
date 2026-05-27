"""Built-in paper format check tool manifest and handler."""

from __future__ import annotations

from typing import Any


TOOL_MANIFESTS = [
    {
        "tool_key": "file.paper_format_check",
        "display_name": "论文查非与格式检查",
        "description": "对 docx、tex、pdf 论文执行结构、格式、文字规范和模板差异检查，生成辅助审阅报告。",
        "tool_type": "native",
        "category": "file_parse",
        "handler_path": "agent.tools.builtin.paper_format_tools.check",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "parsed": {"type": "object", "description": "已解析的文档结构"},
                "file_name": {"type": "string", "description": "文件名"},
                "query": {"type": "string", "description": "用户查询文本"},
                "template_id": {"type": "string", "description": "模板ID"},
            },
            "required": ["parsed", "file_name"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "description": "综合评分"},
                "issues": {"type": "array", "description": "问题列表"},
                "limitations": {"type": "array", "description": "局限性说明"},
                "summary": {"type": "string", "description": "检查总结"},
            },
        },
        "risk_level": "low",
        "is_readonly": True,
    },
]


def check(
    parsed: dict[str, Any],
    file_name: str,
    query: str = "",
    template_id: str | None = None,
) -> dict[str, Any]:
    from agent.tools.paper_format_checker import check_paper_format

    result = check_paper_format(
        parsed=parsed,
        file_name=file_name,
        query=query,
        template_id=template_id,
    )
    return {
        "score": result.get("score", 0),
        "issues": result.get("issues", []),
        "limitations": result.get("limitations", []),
        "summary": result.get("summary", ""),
        "document_type": result.get("document_type", "unknown"),
        "template_id": result.get("template_id"),
    }
