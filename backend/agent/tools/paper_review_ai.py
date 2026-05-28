"""""Ai-Review model step for paper format review reports."""""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from app.services.model_config_service import ModelConfigService


class PaperReviewModelError(RuntimeError):
    """论文查非 AI Review 模型调用失败。不上报兜底结果，直接向前端报错。"""
    pass


PROMPT_KEY = "chat.paper_format_check.system"
DEFAULT_AI_REVIEW_PROMPT = """你是论文格式与规范审阅助手。

你只能基于 rule_report 中的 issues、evidence、retrieved_template_clauses 生成审阅报告。
规则引擎已经完成客观判断，你不需要重新判断论文是否违规。

严格规则：
1. 每条 issue 必须给出：问题描述 -> 违规证据 -> 模板依据 -> 影响 -> 具体修改方案
2. 模板依据必须来自 retrieved_template_clauses，不得编造模板条款
3. 不得新增没有 evidence 支撑的问题
4. 不得编造论文内容、学校名称、参考文献信息
5. 没有证据支撑的问题必须拒绝输出
6. 输出必须是合法 JSON，不要输出 JSON 之外的任何文本

返回 JSON 格式（所有字段必填）：
{
  "answer": "不超过200字的简要总结",
  "summary": "一句话结论",
  "markdown_report": "完整 Markdown 审阅报告，包含总体评价、逐问题详述、模板对比结论、修改优先级建议。不得少于500字。不要自行生成局限性或人工复核段落。",
  "issues": [
    {
      "code": "issue code",
      "title": "问题简述",
      "severity": "high|medium|low",
      "location": "具体段落/章节位置",
      "evidence": "实际违规证据文本",
      "template_basis": "模板条款依据（引用自retrieved_template_clauses）",
      "impact": "不符合模板/规范的后果说明",
      "suggestion": "具体的、可执行的修改建议",
      "need_human_review": false
    }
  ],
  "limitations": ["只能逐字复制 Review Evidence Pack.limitations 中已有的条目；如果为空则返回空数组"],
  "download_title": "论文查非与格式审阅报告"
}"""

_MISLEADING_LIMITATION_PATTERNS = (
    "仅基于规则引擎",
    "规则引擎自动识别",
    "图表格式",
    "页眉页脚",
    "参考文献著录格式",
    "未覆盖",
    "需人工复核",
    "人工复核",
    "第1段证据",
    "仅依据第1段",
    "其他段落可能",
    "全面核查",
)

_TODAY = date.today().isoformat()


async def generate_ai_review_output(
    *,
    evidence_pack: dict[str, Any],
    guide_evidence: dict[str, Any] | None = None,
    query: str,
    db_session: Any,
    org_id: str,
    trace_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Generate Ai-Review JSON from structured evidence using configured chat model."""

    if db_session is None:
        raise PaperReviewModelError("未传入数据库会话，无法读取模型配置。")

    try:
        models = await ModelConfigService(db_session, org_id).list_runtime_models()
        runtime = await LLMGateway().select_runtime(
            models=models,
            model_types={"chat"},
            reserve=False,
        )
    except Exception as exc:
        raise PaperReviewModelError(f"读取模型配置失败：{exc}") from exc

    if not runtime:
        raise PaperReviewModelError("未找到可用的聊天模型配置。")

    prompt = await _resolve_system_prompt(org_id=org_id)
    client = LLMClient(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        model_id=runtime.get("model_id"),
        provider=runtime.get("provider"),
        trace_id=trace_id,
        task_id=task_id,
        org_id=org_id,
        input_price_per_million=runtime.get("input_price_per_million"),
        output_price_per_million=runtime.get("output_price_per_million"),
    )

    try:
        messages = build_ai_review_messages(
            query=query,
            evidence_pack=evidence_pack,
            guide_evidence=guide_evidence,
            system_prompt=prompt,
        )
        response = await client.chat(
            messages,
            temperature=0.2,
            observation_name="paper.ai_review",
            observation_metadata={
                "prompt_key": PROMPT_KEY,
                "document_type": (evidence_pack.get("document") or {}).get("document_type"),
                "template_id": (evidence_pack.get("document") or {}).get("template_id"),
            },
        )
    except Exception as exc:
        raise PaperReviewModelError(f"Ai-Review 模型调用失败：{exc}") from exc

    normalized = normalize_ai_review_output(response)
    normalized["limitations"] = _sanitize_ai_limitations(
        normalized.get("limitations") or [],
        allowed=list(evidence_pack.get("limitations") or []),
    )
    normalized["markdown_report"] = _sanitize_ai_markdown_report(
        str(normalized.get("markdown_report") or "")
    )
    if not normalized.get("markdown_report"):
        raise PaperReviewModelError("Ai-Review 返回内容缺少 markdown_report。")

    if isinstance(response.get("__meta__"), dict):
        normalized["model_meta"] = response["__meta__"]

    normalized["model_used"] = True
    if guide_evidence:
        normalized.setdefault("review_sources", {})
        normalized["review_sources"] = {
            **dict(normalized.get("review_sources") or {}),
            "rule_template": str((evidence_pack.get("document") or {}).get("template_id") or ""),
            "writing_guide": str(guide_evidence.get("file_name") or ""),
        }
    return normalized


def build_ai_review_messages(
    *,
    query: str,
    evidence_pack: dict[str, Any],
    guide_evidence: dict[str, Any] | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    document = evidence_pack.get("document") or {}
    issues = list(evidence_pack.get("issues") or [])
    trimmed_issues = _trim_issues_for_model(issues, max_high=20, max_medium=10, max_low_abstract=5)

    clauses_section = ""
    if guide_evidence and not guide_evidence.get("error"):
        clauses = guide_evidence.get("clauses") or []
        if clauses:
            clauses_section = (
                "\n\n检索到的模板条款（你只能引用这些条款作为依据）：\n"
                f"{json.dumps(clauses, ensure_ascii=False, default=str)}"
            )

    model_input = {
        "task": {"type": "paper_format_ai_review", "language": "zh-CN", "output_format": "json"},
        "document": document,
        "rule_report": {
            "score": evidence_pack.get("score", 0),
            "issue_count": len(issues),
            "high_count": sum(1 for i in issues if i.get("severity") == "high"),
            "medium_count": sum(1 for i in issues if i.get("severity") == "medium"),
            "low_count": sum(1 for i in issues if i.get("severity") == "low"),
            "issues": trimmed_issues,
        },
        "style_summary": evidence_pack.get("style_summary") or {},
        "limitations": list(evidence_pack.get("limitations") or []),
    }

    user_content = (
        f"当前日期：{_TODAY}\n\n"
        f"用户问题：\n{query or '请进行论文查非与格式审阅'}\n\n"
        f"Review Evidence Pack：\n{json.dumps(model_input, ensure_ascii=False, default=str)}"
        f"{clauses_section}\n\n"
        "请基于以上证据生成完整审阅报告 JSON。"
        "markdown_report 必须详细充实，不少于500字。"
        "不得编造任何不在 issues 或 template_clauses 中的内容。"
        "limitations 只能逐字复制 Review Evidence Pack.limitations，不能自行扩展为“规则引擎未覆盖/需人工复核/仅第1段证据”等结论。"
        "不要输出 JSON 以外的文本。"
    )
    return [
        {"role": "system", "content": system_prompt or DEFAULT_AI_REVIEW_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _trim_issues_for_model(
    issues: list[dict[str, Any]],
    max_high: int = 20,
    max_medium: int = 10,
    max_low_abstract: int = 5,
) -> list[dict[str, Any]]:
    high = [i for i in issues if i.get("severity") == "high"][:max_high]
    medium = [i for i in issues if i.get("severity") == "medium"][:max_medium]
    low = [i for i in issues if i.get("severity") == "low"]
    low_abstract = low[:max_low_abstract]
    if len(low) > max_low_abstract:
        low_abstract.append({
            "code": "summary.low_severity_omitted",
            "title": f"另有 {len(low) - max_low_abstract} 个低严重性问题",
            "severity": "low",
            "message": f"完整列表共 {len(low)} 项低严重性问题，此处仅展示前 {max_low_abstract} 项，详见下载报告。",
        })
    return high + medium + low_abstract


def normalize_ai_review_output(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = _extract_payload(raw or {})
    issues = payload.get("issues")
    if not isinstance(issues, list):
        issues = []
    limitations = payload.get("limitations")
    if not isinstance(limitations, list):
        limitations = []
    return {
        "answer": str(payload.get("answer") or ""),
        "summary": str(payload.get("summary") or ""),
        "markdown_report": str(payload.get("markdown_report") or ""),
        "issues": [item for item in issues if isinstance(item, dict)],
        "limitations": [str(item) for item in limitations],
        "download_title": str(payload.get("download_title") or "论文查非辅助报告"),
    }


def _sanitize_ai_limitations(limitations: list[Any], *, allowed: list[Any]) -> list[str]:
    allowed_texts = [str(item).strip() for item in allowed if str(item).strip()]
    allowed_set = set(allowed_texts)
    sanitized: list[str] = []
    for item in limitations:
        text = str(item).strip()
        if not text:
            continue
        if text in allowed_set and text not in sanitized:
            sanitized.append(text)
            continue
        if any(pattern in text for pattern in _MISLEADING_LIMITATION_PATTERNS):
            continue
    return sanitized


def _sanitize_ai_markdown_report(markdown: str) -> str:
    lines = str(markdown or "").splitlines()
    cleaned: list[str] = []
    skip_section = False
    skip_level = 0
    for line in lines:
        stripped = line.strip()
        heading = _markdown_heading_level(stripped)
        if heading:
            title = stripped.lstrip("#").strip()
            if "局限性" in title or "人工复核" in title:
                skip_section = True
                skip_level = heading
                continue
            if skip_section and heading <= skip_level:
                skip_section = False
        if skip_section:
            continue
        if any(pattern in stripped for pattern in _MISLEADING_LIMITATION_PATTERNS):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _markdown_heading_level(line: str) -> int:
    if not line.startswith("#"):
        return 0
    level = len(line) - len(line.lstrip("#"))
    if level <= 6 and line[level:level + 1] == " ":
        return level
    return 0


async def _resolve_system_prompt(*, org_id: str) -> str:
    try:
        from app.services.prompt_admin_service import PromptResolver
        from infra.database.session import get_session

        resolved = await PromptResolver(get_session).get(PROMPT_KEY, org_id=org_id)
        return str(resolved or DEFAULT_AI_REVIEW_PROMPT)
    except Exception:
        return DEFAULT_AI_REVIEW_PROMPT


def _extract_payload(raw: dict[str, Any]) -> dict[str, Any]:
    if any(key in raw for key in ("answer", "summary", "markdown_report", "issues")):
        return raw
    text = raw.get("text")
    if isinstance(text, str) and text.strip():
        parsed = _parse_json_object(text)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _parse_json_object(text: str) -> dict[str, Any] | None:
    candidates = [text.strip()]
    if "```" in text:
        import re

        candidates.extend(
            block.strip()
            for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
        )
    for candidate in candidates:
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
