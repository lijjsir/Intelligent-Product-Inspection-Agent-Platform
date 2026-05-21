"""Built-in report generation tool manifest and handler."""

from __future__ import annotations

from agent.tools.report_generate import run as report_generate_run


TOOL_MANIFESTS = [
    {
        "tool_key": "report.generate",
        "display_name": "检测报告生成",
        "description": "根据检测结果自动生成格式化检测报告，支持 PDF 和 HTML 输出。",
        "tool_type": "native",
        "category": "report_gen",
        "handler_path": "agent.tools.builtin.report_tools.generate",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "inspection_id": {"type": "string", "description": "检测任务 ID"},
                "format": {"type": "string", "enum": ["pdf", "html"], "default": "pdf"},
                "template": {"type": "string", "description": "模板名称"},
            },
            "required": ["inspection_id"],
        },
        "returns_schema": {"type": "object", "properties": {"report_url": {"type": "string"}}},
        "risk_level": "medium",
        "is_readonly": False,
    },
]


async def generate(inspection_id: str, format: str = "pdf", template: str | None = None) -> dict:
    base = await report_generate_run(
        {
            "inspection_id": inspection_id,
            "format": format,
            "template": template,
        }
    )
    report_url = base.get("report_url") or f"/api/v1/reports/{inspection_id}.{format}"
    return {
        "inspection_id": inspection_id,
        "format": format,
        "template": template,
        "report_url": report_url,
    }
