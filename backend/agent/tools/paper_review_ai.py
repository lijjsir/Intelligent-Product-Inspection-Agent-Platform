"""""Ai-Review model step for paper format review reports."""""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from app.services.model_config_service import ModelConfigService


PROMPT_KEY = "chat.paper_format_check.system"
DEFAULT_AI_REVIEW_PROMPT = """你是论文格式与规范审阅助手，严格按照专业审阅报告格式输出。

你将收到用户问题和 Review Evidence Pack。Evidence Pack 包含：
1. 结构化规则检查结果（客观问题清单，不是建议）
2. 证据片段（违规段落的实际文本）
3. 样式摘要（实际字体、行距、页边距等数据）
4. 模板写作规范参考（目标格式要求）

你的核心任务：
1. 基于规则检查发现的客观问题，逐条生成具体的修改建议。
2. 对于每条问题，必须给出：问题描述 → 违规证据 → 影响 → 具体修改方案。
3. 没有确凿证据的问题必须标注 need_human_review=true，并在 evidence 中写"需人工核对"。
4. 如果提供了模板写作规范，将实际样式数据与模板要求逐项对比，明确指出差异。
5. 严禁编造论文内容、学校名称、模板条款或参考文献信息。
6. 优先输出高严重性问题，再输出中低严重性问题。
7. 输出的 markdown_report 要完整、可读、可直接下载为正式审阅报告。
8. 只返回 JSON，不要输出任何 JSON 之外的文本。

返回 JSON 格式（所有字段必填）：
{
  "answer": "不超过200字的简要总结，列出关键问题和评分",
  "summary": "一句话结论",
  "markdown_report": "格式完整的 Markdown 审阅报告，包含：总体评价、逐问题详述、模板对比结论、局限性说明、修改优先级建议。不得少于500字。",
  "issues": [
    {
      "title": "问题简述",
      "severity": "high|medium|low",
      "category": "structure|style|text|template",
      "location": "具体段落/章节位置",
      "evidence": "实际违规证据文本",
      "impact": "不符合模板/规范的后果说明",
      "suggestion": "具体的、可执行的修改建议",
      "need_human_review": false
    }
  ],
  "limitations": ["当前检查的局限性说明"],
  "download_title": "论文查非辅助报告"
}

特别注意：
- 如果用户未选择严格模板（template_id=generic_cn_thesis），你只能按通用学术规范提出建议，并说明"未指定学校模板，以下建议基于通用规范"。
- 如果 PDF/LaTeX 解析无法获取完整版式信息，必须在 limitations 中写明。
"""

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
        return _fallback_output("未传入数据库会话，无法读取模型配置。")

    try:
        models = await ModelConfigService(db_session, org_id).list_runtime_models()
        runtime = await LLMGateway().select_runtime(
            models=models,
            model_types={"chat"},
            reserve=False,
        )
    except Exception as exc:
        return _fallback_output(f"读取模型配置失败：{exc}")

    if not runtime:
        return _fallback_output("未找到可用的聊天模型配置，已使用规则检查结果生成报告。")

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
            guide_evidence=None,
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
        return _fallback_output(f"Ai-Review 模型调用失败：{exc}")

    normalized = normalize_ai_review_output(response)
    if isinstance(response.get("__meta__"), dict):
        normalized["model_meta"] = response["__meta__"]

    if guide_evidence:
        try:
            guide_messages = build_writing_guide_review_messages(
                query=query,
                evidence_pack=evidence_pack,
                guide_evidence=guide_evidence,
                system_prompt=prompt,
            )
            guide_response = await client.chat(
                guide_messages,
                temperature=0.2,
                observation_name="paper.ai_review.writing_guide",
                observation_metadata={
                    "prompt_key": PROMPT_KEY,
                    "template_id": guide_evidence.get("template_id"),
                    "guide_role": guide_evidence.get("role"),
                },
            )
            guide_output = normalize_ai_review_output(guide_response)
            if isinstance(guide_response.get("__meta__"), dict):
                guide_output["model_meta"] = guide_response["__meta__"]
            normalized = merge_ai_review_outputs(
                rule_output=normalized,
                guide_output=guide_output,
                evidence_pack=evidence_pack,
                guide_evidence=guide_evidence,
            )
        except Exception as exc:
            normalized.setdefault("limitations", []).append(
                f"writing guide review failed: {exc}"
            )

    normalized["model_used"] = True
    if guide_evidence:
        normalized.setdefault("limitations", []).append(
            f"已参考模板写作指南：{guide_evidence.get('file_name', '')}"
        )
    return normalized


def build_ai_review_messages(
    *,
    query: str,
    evidence_pack: dict[str, Any],
    guide_evidence: dict[str, Any] | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    evidence_json = json.dumps(evidence_pack, ensure_ascii=False, default=str)
    guide_section = ""
    if guide_evidence:
        guide_section = (
            f"\n\n模板写作规范参考（{guide_evidence.get('template_name', '')}）：\n"
            f"{json.dumps(guide_evidence, ensure_ascii=False, default=str)}"
        )
    user_content = (
        f"当前日期：{_TODAY}\n\n"
        f"用户问题：\n{query or '请进行论文查非与格式审阅'}\n\n"
        "Review Evidence Pack（包含结构化检查结果、issue 清单、证据片段、样式摘要）：\n"
        f"{evidence_json}"
        f"{guide_section}\n\n"
        "请基于以上证据生成完整审阅报告 JSON。"
        "markdown_report 必须详细充实，不少于500字。"
        "如果提供了模板写作规范，将实际样式与模板要求逐项对比。"
        "不要输出 JSON 以外的文本。"
    )
    return [
        {"role": "system", "content": system_prompt or DEFAULT_AI_REVIEW_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_writing_guide_review_messages(
    *,
    query: str,
    evidence_pack: dict[str, Any],
    guide_evidence: dict[str, Any],
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    payload = {
        "document": evidence_pack.get("document") or {},
        "rule_issues": list(evidence_pack.get("issues") or []),
        "limitations": list(evidence_pack.get("limitations") or []),
        "writing_guide": guide_evidence,
    }
    guide_json = json.dumps(payload, ensure_ascii=False, default=str)
    user_content = (
        f"用户问题：\n{query or '请进行论文查非与格式审阅'}\n\n"
        "Writing Guide Evidence：\n"
        f"{guide_json}\n\n"
        "请只基于写作指南证据和规则检查结果，补充生成 JSON。"
        "没有规则证据支撑的新问题必须标注 need_human_review=true。"
        "不要输出 JSON 以外的文本。"
    )
    return [
        {"role": "system", "content": system_prompt or DEFAULT_AI_REVIEW_PROMPT},
        {"role": "user", "content": user_content},
    ]


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


def merge_ai_review_outputs(
    *,
    rule_output: dict[str, Any],
    guide_output: dict[str, Any],
    evidence_pack: dict[str, Any],
    guide_evidence: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(rule_output)
    rule_markdown = str(rule_output.get("markdown_report") or "").strip()
    guide_markdown = str(guide_output.get("markdown_report") or "").strip()
    if guide_markdown:
        merged["markdown_report"] = "\n\n".join(
            item
            for item in [rule_markdown, "## 写作指南补充评判", guide_markdown]
            if item
        )
    merged["answer"] = _join_sentences(rule_output.get("answer"), guide_output.get("answer"))
    merged["summary"] = _join_sentences(rule_output.get("summary"), guide_output.get("summary"))
    merged["guide_review_output"] = guide_output
    merged["guide_issues"] = list(guide_output.get("issues") or [])
    merged["limitations"] = list(
        dict.fromkeys(
            [
                *list(rule_output.get("limitations") or []),
                *list(guide_output.get("limitations") or []),
            ]
        )
    )
    merged["review_sources"] = {
        "rule_template": str((evidence_pack.get("document") or {}).get("template_id") or ""),
        "writing_guide": str(guide_evidence.get("file_name") or ""),
    }
    return merged


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


def _fallback_output(reason: str) -> dict[str, Any]:
    return {
        "answer": "",
        "summary": "",
        "markdown_report": "",
        "issues": [],
        "limitations": [reason],
        "download_title": "论文查非辅助报告",
        "model_used": False,
    }


def _join_sentences(*values: Any) -> str:
    parts = [str(value).strip() for value in values if str(value or "").strip()]
    return " ".join(parts)
