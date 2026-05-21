"""Built-in inspection calculation tool manifests and handlers."""

from __future__ import annotations

from collections.abc import Mapping


TOOL_MANIFESTS = [
    {
        "tool_key": "calc.inspection_score",
        "display_name": "检测评分计算",
        "description": "根据检测标准和证据片段自动计算产品质量评分。",
        "tool_type": "native",
        "category": "inspection_calc",
        "handler_path": "agent.tools.builtin.inspection_tools.calc_score",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "standard_id": {"type": "string", "description": "检测标准 ID"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["standard_id", "evidence_ids"],
        },
        "returns_schema": {"type": "object", "properties": {"score": {"type": "number"}, "details": {"type": "array"}}},
        "risk_level": "medium",
        "is_readonly": False,
    },
    {
        "tool_key": "calc.standard_compare",
        "display_name": "检测标准比对",
        "description": "将检测结果与标准值进行自动比对，标记偏离项。",
        "tool_type": "native",
        "category": "inspection_calc",
        "handler_path": "agent.tools.builtin.inspection_tools.compare",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "result_data": {"type": "object"},
                "standard_values": {"type": "object"},
            },
            "required": ["result_data", "standard_values"],
        },
        "returns_schema": {"type": "object", "properties": {"deviations": {"type": "array"}}},
        "risk_level": "low",
        "is_readonly": True,
    },
]


def calc_score(standard_id: str, evidence_ids: list[str]) -> dict:
    evidence_count = len(evidence_ids)
    score = min(100.0, round(60 + evidence_count * 8, 2))
    return {
        "standard_id": standard_id,
        "score": score,
        "details": [
            {
                "rule": "evidence_coverage",
                "matched_count": evidence_count,
                "weight": 8,
            }
        ],
    }


def compare(result_data: dict, standard_values: dict) -> dict:
    deviations = []
    for key, expected in standard_values.items():
        actual = result_data.get(key)
        if actual != expected:
            deviations.append(
                {
                    "field": key,
                    "expected": _normalize(expected),
                    "actual": _normalize(actual),
                }
            )

    extra_fields = sorted(set(result_data) - set(standard_values))
    for key in extra_fields:
        deviations.append(
            {
                "field": key,
                "expected": None,
                "actual": _normalize(result_data.get(key)),
            }
        )

    return {"deviations": deviations, "matched": len(deviations) == 0}


def _normalize(value):
    if isinstance(value, Mapping):
        return dict(value)
    return value
