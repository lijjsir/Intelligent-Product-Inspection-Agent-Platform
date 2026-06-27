from __future__ import annotations

import json
from typing import Any

from agent.subgraphs.lab_detection.contracts import LabPartialDataContext


LAB_EARLY_RISK_SYSTEM_PROMPT = """
你是质量监管系统中的 Lab Detection Agent，负责真实实验室检测过程中的早期异常研判。

你会收到一个尚未完成的实验室检测任务，其中只有部分检测项目已经产生数据。
你的任务不是给出最终合格或不合格结论，而是在完整检测结果形成之前，判断已完成的部分检测数据是否已经呈现异常趋势。

你需要综合考虑：
1. 已完成检测项与标准限值的关系；
2. 已完成检测项与历史正常响应区间的偏离程度；
3. 当前检测项目完成比例；
4. 设备响应是否可能异常；
5. 环境因素是否可能影响检测结果；
6. 尚未完成检测项对最终结论的重要性；
7. 当前是否需要提前触发风险预警；
8. 哪些后续检测项应该优先执行；
9. 当前是否需要人工复核。

严格要求：
1. 不允许直接给出最终合格结论；
2. 不允许直接给出最终不合格结论；
3. can_make_final_verdict 必须为 false；
4. 检测数据不足时必须输出 insufficient_data 或 uncertain_continue；
5. 如果已有指标明显超过标准限值，可以输出 early_abnormal；
6. 如果异常可能来自设备、环境或数据质量问题，必须标记 manual_review_required；
7. 每个异常判断必须绑定具体检测指标；
8. 每个建议补测项目必须说明原因；
9. 不允许编造标准限值；
10. 不允许编造历史正常响应模式；
11. 输出必须是 JSON，不要输出 Markdown；
12. assessment_state 只能是 normal_so_far、early_abnormal、uncertain_continue、insufficient_data、manual_review_required 之一。
"""


def build_lab_early_risk_user_prompt(
    *,
    context: LabPartialDataContext,
    anomaly_features: list[dict[str, Any]],
    deterministic_summary: dict[str, Any],
    standard_limits: list[dict[str, Any]],
    normal_profile: dict[str, Any],
) -> str:
    payload = {
        "task": "基于部分实验室检测数据进行早期异常研判",
        "context": context.model_dump(),
        "standard_limits": standard_limits,
        "normal_profile": normal_profile,
        "anomaly_features": anomaly_features,
        "deterministic_summary": deterministic_summary,
        "required_output_schema": {
            "assessment_state": "normal_so_far | early_abnormal | uncertain_continue | insufficient_data | manual_review_required",
            "abnormal_probability": "0.0-1.0",
            "risk_level": "low | medium | high | critical",
            "early_warning": "boolean",
            "can_make_final_verdict": False,
            "suggested_action": "continue_testing | priority_followup_test | manual_review | wait_for_more_data",
            "next_test_priority": [
                {
                    "item": "检测项目名称",
                    "priority": "low | medium | high",
                    "reason": "为什么优先补测",
                }
            ],
            "explanation": "自然语言解释",
            "requires_manual_review": "boolean",
            "confidence": "0.0-1.0",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
