"""Built-in quality operation tool manifests for DB sync."""

from __future__ import annotations

TOOL_MANIFESTS = [
    {
        "tool_key": "quality.task.status",
        "display_name": "检测任务状态查询",
        "description": "查询质量检测任务的当前状态、进度和基本信息。需要提供 task_id。",
        "tool_type": "native",
        "category": "quality",
        "handler_path": "agent.tools.builtin.quality_tools.task_status",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "检测任务 ID"},
            },
            "required": ["task_id"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {"type": "string"},
                "product_id": {"type": "string"},
                "spec_code": {"type": "string"},
            },
        },
        "risk_level": "low",
        "is_readonly": True,
    },
    {
        "tool_key": "quality.report.query",
        "display_name": "历史报告查询",
        "description": "查询历史检测报告和结果，支持按产品 ID 过滤。",
        "tool_type": "native",
        "category": "quality",
        "handler_path": "agent.tools.builtin.quality_tools.report_query",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "产品编号（可选）"},
                "limit": {"type": "integer", "default": 10, "description": "返回条数上限"},
            },
            "required": [],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "reports": {"type": "array"},
                "total": {"type": "integer"},
            },
        },
        "risk_level": "low",
        "is_readonly": True,
    },
    {
        "tool_key": "quality.inspection.execute",
        "display_name": "正式质量检测执行",
        "description": "创建并执行正式质量检测任务，仅质量检测任务页面可调用。需确认后执行。",
        "tool_type": "native",
        "category": "quality",
        "handler_path": "agent.tools.builtin.quality_tools.inspection_execute",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "产品编号"},
                "spec_code": {"type": "string", "description": "检测标准编码"},
                "image_urls": {"type": "array", "items": {"type": "string"}, "description": "检测图片列表"},
                "priority": {"type": "integer", "default": 5},
            },
            "required": ["product_id", "spec_code"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {"type": "string"},
            },
        },
        "risk_level": "high",
        "is_readonly": False,
    },
]
