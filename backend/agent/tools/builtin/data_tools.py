"""Built-in data analysis tool manifest for DB sync."""

from __future__ import annotations

TOOL_MANIFESTS = [
    {
        "tool_key": "data.analysis",
        "display_name": "数据分析",
        "description": "查询检测统计数据、趋势、合格率汇总等分析结果。支持 pass_rate、defect_trend、inspection_volume 三种指标。",
        "tool_type": "native",
        "category": "data",
        "handler_path": "agent.tools.builtin.data_tools.analysis",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "description": "分析指标：pass_rate（合格率）、defect_trend（缺陷趋势）、inspection_volume（检测量）",
                    "enum": ["pass_rate", "defect_trend", "inspection_volume"],
                },
                "product_id": {"type": "string", "description": "产品 ID（可选）"},
                "days": {"type": "integer", "default": 30, "description": "统计天数"},
            },
            "required": ["metric"],
        },
        "returns_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "array"},
                "summary": {"type": "string"},
                "metric": {"type": "string"},
            },
        },
        "risk_level": "low",
        "is_readonly": True,
    },
]
