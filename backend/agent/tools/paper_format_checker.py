from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from agent.tools.paper_format_templates import get_paper_template
from agent.tools.paper_review_pycorrector import (
    PycorrectorUnavailableError,
    normalize_pycorrector_errors,
    run_pycorrector,
)
from agent.tools.paper_review_macro_correct import (
    MacroCorrectUnavailableError,
    run_macro_correct_punct,
    run_macro_correct_token,
)
from app.core.config import settings
from app.services.paper_review_runtime_service import (
    PaperReviewDependencyError,
    PaperReviewRuntimeService,
)


DEFAULT_TEMPLATE_ID = "generic_cn_thesis"
logger = logging.getLogger(__name__)

_ZH_PUNCT = "，。；：？！、''‘’（）《》【】"
_EN_PUNCT = ",.;:?!()[]\"'"
_SECTION_CMD_LEVEL = {
    "part": 0,
    "chapter": 1,
    "section": 2,
    "subsection": 3,
    "subsubsection": 4,
}


@dataclass(frozen=True)
class RuleIssue:
    code: str
    title: str
    severity: str
    category: str
    message: str
    evidence: str
    location: dict[str, Any]
    suggestion: str
    expected: dict[str, Any] | None = None
    actual: dict[str, Any] | None = None
    source_clause_ids: list[str] | None = None
    parser_confidence: str = "medium"
    engine: str = "rule"
    engine_rule_id: str | None = None
    confidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "code": self.code,
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "evidence": self.evidence,
            "location": dict(self.location),
            "suggestion": self.suggestion,
            "parser_confidence": self.parser_confidence,
            "engine": self.engine,
        }
        if self.expected:
            result["expected"] = dict(self.expected)
        if self.actual:
            result["actual"] = dict(self.actual)
        if self.source_clause_ids:
            result["source_clause_ids"] = list(self.source_clause_ids)
        if self.engine_rule_id:
            result["engine_rule_id"] = self.engine_rule_id
        if self.confidence:
            result["confidence"] = self.confidence
        return result


def check_paper_format(
    *,
    parsed: dict[str, Any],
    file_name: str,
    query: str,
    template_id: str | None = None,
) -> dict[str, Any]:
    document_type = str(parsed.get("kind") or "text")
    effective_template_id = template_id or DEFAULT_TEMPLATE_ID
    template = get_paper_template(effective_template_id)
    effective_template_id = str(template.get("template_id") or effective_template_id)
    is_generic_template = effective_template_id == DEFAULT_TEMPLATE_ID and not bool(template_id)
    issues: list[RuleIssue] = []
    limitations: list[str] = []
    runtime_status: dict[str, Any] | None = None

    if document_type == "docx":
        runtime_status = PaperReviewRuntimeService.diagnose_sync()
        parser_limitations = [str(item) for item in list(parsed.get("parser_limitations") or []) if str(item).strip()]
        limitations.extend(parser_limitations)
        if not runtime_status.get("ok"):
            detail = "; ".join(
                f"{item['name']}: {item.get('detail') or 'unavailable'}"
                for item in list(runtime_status.get("engine_status") or [])
                if not item.get("ok")
            )
            limitations.append("论文检测环境未就绪，已终止 docx 增强校验。")
            return {
                "document_type": document_type,
                "template_id": effective_template_id,
                "summary": "论文检测环境未就绪，当前无法完成 docx 增强校验。",
                "score": 0,
                "issues": [],
                "limitations": list(dict.fromkeys(limitations)),
                "query": query,
                "engines_used": list(runtime_status.get("engines_used") or []),
                "engine_status": list(runtime_status.get("engine_status") or []),
                "runtime_ready": False,
                "chat_advice": "论文检测环境未就绪，请先安装并配置 python-docx、lxml、pycorrector、macro-correct、LanguageTool 和 Vale 后重试。",
            }

    if document_type == "docx":
        issues.extend(_check_docx_structure(parsed))
        issues.extend(_check_template_rules(parsed, template=template, document_type=document_type))
        issues.extend(_check_docx_style(parsed))
        issues.extend(_check_front_matter_rules(parsed, template=template, document_type=document_type))
        issues.extend(_check_toc_rules(parsed, template=template))
        issues.extend(_check_heading_rules(parsed))
        issues.extend(_check_figure_table_rules(parsed))
        issues.extend(_check_formula_rules(parsed))
        issues.extend(_check_reference_rules(parsed))
        issues.extend(_check_word_artifact_rules(parsed))
        issues.extend(_run_docx_text_engines(parsed, file_name=file_name))
    elif document_type == "tex":
        issues.extend(_check_tex_structure(parsed))
        issues.extend(_check_text_norms(parsed))
        issues.extend(_check_template_rules(parsed, template=template, document_type=document_type))
        issues.extend(_check_front_matter_rules(parsed, template=template, document_type=document_type))
        issues.extend(_check_heading_rules(parsed))
        issues.extend(_check_figure_table_rules(parsed))
        issues.extend(_check_formula_rules(parsed))
        issues.extend(_check_reference_rules(parsed))
        limitations.append("LaTeX 仅基于源码检查，不代表最终 PDF 版面完全合规。")
    elif document_type == "pdf":
        issues.extend(_check_pdf_structure(parsed))
        issues.extend(_check_text_norms(parsed))
        issues.extend(_check_template_rules(parsed, template=template, document_type=document_type))
        issues.extend(_check_front_matter_rules(parsed, template=template, document_type=document_type))
        issues.extend(_check_heading_rules(parsed))
        issues.extend(_check_figure_table_rules(parsed))
        issues.extend(_check_formula_rules(parsed))
        issues.extend(_check_reference_rules(parsed))
        limitations.append("当前 PDF 检查主要基于文本抽取，不能完整判断字号、页边距、行距等版面格式。")
    else:
        limitations.append("当前仅支持 docx、pdf 和 tex 的论文查非检查。")
        issues.append(
            RuleIssue(
                code="unsupported.document_type",
                title="暂不支持的文档类型",
                severity="high",
                category="support",
                message="当前论文查非仅支持 docx、pdf 和 tex 文件。",
                evidence=file_name,
                location={"file": file_name},
                suggestion="请上传 docx、pdf 或 tex 文档。",
            )
        )

    if is_generic_template:
        limitations.append("未指定模板，当前使用内置通用论文规则，无法做严格模板校验。")
    elif effective_template_id == "cqupt_graduate_thesis_2022":
        limitations.append("已使用重庆邮电大学研究生学位论文模板（2022版）规则进行辅助校验，仍需以学校最新正式文件为准。")

    issues = _dedupe_issues(issues)
    summary = _build_summary(document_type=document_type, issues=issues, limitations=limitations)

    return {
        "document_type": document_type,
        "template_id": effective_template_id,
        "summary": summary,
        "score": _score_issues(issues),
        "issues": [item.to_dict() for item in issues],
        "limitations": limitations,
        "query": query,
        "engines_used": list((runtime_status or {}).get("engines_used") or ["rule"]),
        "engine_status": list((runtime_status or {}).get("engine_status") or [{"name": "rule", "ok": True, "detail": "built-in"}]),
        "runtime_ready": bool(runtime_status.get("ok")) if runtime_status is not None else True,
    }


def _build_summary(*, document_type: str, issues: list[RuleIssue], limitations: list[str]) -> str:
    if not issues:
        base = f"已完成 {document_type} 论文查非检查，未发现明显的格式或文字规范问题。"
    else:
        high = sum(1 for item in issues if item.severity == "high")
        medium = sum(1 for item in issues if item.severity == "medium")
        low = sum(1 for item in issues if item.severity == "low")
        base = (
            f"已完成 {document_type} 论文查非检查，共发现 {len(issues)} 个问题，"
            f"其中高优先级 {high} 个、中优先级 {medium} 个、低优先级 {low} 个。"
        )
    if limitations:
        base = f"{base} 结果存在范围限制：{limitations[0]}"
    return base


def _score_issues(issues: list[RuleIssue]) -> int:
    score = 100
    for item in issues:
        if item.severity == "high":
            score -= 12
        elif item.severity == "medium":
            score -= 6
        else:
            score -= 2
    return max(0, score)


def _issue_location_from_paragraph(
    paragraph: dict[str, Any] | None,
    *,
    fallback_section: str | None = None,
) -> dict[str, Any]:
    paragraph = paragraph or {}
    location: dict[str, Any] = {}
    section_title = str(paragraph.get("section_title") or "").strip()
    section_index = paragraph.get("section_index")
    paragraph_index = paragraph.get("index")
    paragraph_no = paragraph.get("paragraph_no")
    if fallback_section:
        location["section"] = fallback_section
    if section_title:
        location["section_title"] = section_title
    if paragraph_index is not None:
        location["paragraph_index"] = paragraph_index
    if paragraph_no:
        location["paragraph_no"] = paragraph_no
    location["display_text"] = _format_docx_location(
        section_title=section_title,
        section_index=section_index,
        paragraph_no=paragraph_no,
        paragraph_index=paragraph_index,
    )
    return location


def _issue_location_from_tex(
    item: dict[str, Any] | None,
    *,
    fallback_section: str | None = None,
) -> dict[str, Any]:
    item = item or {}
    location: dict[str, Any] = {}
    section_title = str(item.get("section_title") or item.get("title") or "").strip()
    section_index = item.get("section_index")
    line = item.get("line")
    if fallback_section:
        location["section"] = fallback_section
    if section_title:
        location["section_title"] = section_title
    if line is not None:
        location["line"] = line
    location["display_text"] = _format_tex_location(
        section_title=section_title,
        section_index=section_index,
        line=line,
    )
    return location


def _format_docx_location(
    *,
    section_title: str,
    section_index: Any,
    paragraph_no: Any,
    paragraph_index: Any,
) -> str:
    if section_title and paragraph_no:
        prefix = f"第{section_index}节《{section_title}》" if section_index else f"《{section_title}》"
        return f"{prefix}下第{paragraph_no}段"
    if section_title:
        return f"《{section_title}》附近"
    if paragraph_index is not None:
        return f"第 {int(paragraph_index) + 1} 段"
    return "文档位置待人工确认"


def _format_tex_location(
    *,
    section_title: str,
    section_index: Any,
    line: Any,
) -> str:
    if section_title and line is not None:
        prefix = f"第{section_index}节《{section_title}》" if section_index else f"《{section_title}》"
        return f"{prefix}附近，第{line}行"
    if line is not None:
        return f"第 {line} 行"
    return "源码位置待人工确认"


def _find_paragraph_by_offset(parsed: dict[str, Any], offset: int) -> dict[str, Any] | None:
    paragraphs = [item for item in list(parsed.get("paragraphs") or []) if str(item.get("text") or "").strip()]
    cursor = 0
    for paragraph in paragraphs:
        text = str(paragraph.get("text") or "")
        start = cursor
        end = cursor + len(text)
        if start <= offset <= end:
            return paragraph
        cursor = end + 1
    return paragraphs[0] if paragraphs else None


def _normalize_required_section_rule(section: Any) -> dict[str, Any]:
    if isinstance(section, dict):
        label = str(section.get("label") or section.get("key") or "").strip()
        aliases = [str(item).strip() for item in list(section.get("aliases") or []) if str(item).strip()]
        if label and label not in aliases:
            aliases.insert(0, label)
        return {
            "key": str(section.get("key") or label).strip(),
            "label": label,
            "aliases": aliases or ([label] if label else []),
            "severity": str(section.get("severity") or "").strip() or ("high" if label in {"摘要", "参考文献"} else "medium"),
            "match_mode": str(section.get("match_mode") or "heading_or_text").strip() or "heading_or_text",
        }
    label = str(section).strip()
    return {
        "key": label,
        "label": label,
        "aliases": [label] if label else [],
        "severity": "high" if label in {"摘要", "参考文献"} else "medium",
        "match_mode": "heading_or_text",
    }


def _required_section_present(parsed: dict[str, Any], rule: dict[str, Any], *, document_type: str) -> bool:
    aliases = [item for item in list(rule.get("aliases") or []) if item]
    match_mode = str(rule.get("match_mode") or "heading_or_text")
    if document_type == "docx" and match_mode == "body_between_sections":
        return _docx_body_between_sections_exists(parsed, rule)
    headings = list(parsed.get("headings") or [])
    text = str(parsed.get("text") or "")
    if _headings_contain_aliases(headings, aliases):
        return True
    return _contains_any(text, aliases)


def _headings_contain_aliases(headings: list[dict[str, Any]], aliases: list[str]) -> bool:
    normalized_aliases = [alias.strip().lower() for alias in aliases if alias.strip()]
    if not normalized_aliases:
        return False
    for heading in headings:
        heading_text = str(heading.get("text") or "").strip().lower()
        if not heading_text:
            continue
        if any(alias in heading_text for alias in normalized_aliases):
            return True
    return False


def _docx_body_between_sections_exists(parsed: dict[str, Any], rule: dict[str, Any]) -> bool:
    headings = list(parsed.get("headings") or [])
    paragraphs = list(parsed.get("paragraphs") or [])
    if not paragraphs:
        return False
    preface_aliases = ["摘要", "关键词", "关键字", "目录", "引言", "绪论"]
    ending_aliases = ["参考文献", "致谢"]
    start_index = None
    end_index = None
    for heading in headings:
        text = str(heading.get("text") or "").strip()
        paragraph_index = heading.get("paragraph_index")
        if paragraph_index is None:
            continue
        if start_index is None and any(alias in text for alias in preface_aliases):
            start_index = int(paragraph_index)
        if any(alias in text for alias in ending_aliases):
            end_index = int(paragraph_index)
            break
    if start_index is None:
        for paragraph in paragraphs:
            text = str(paragraph.get("text") or "").strip()
            if any(alias in text for alias in preface_aliases):
                start_index = int(paragraph.get("index") or 0)
                break
    candidate_headings = []
    for heading in headings:
        paragraph_index = heading.get("paragraph_index")
        level = int(heading.get("level") or 0)
        if paragraph_index is None or level != 1:
            continue
        paragraph_index = int(paragraph_index)
        if start_index is not None and paragraph_index <= start_index:
            continue
        if end_index is not None and paragraph_index >= end_index:
            continue
        candidate_headings.append(heading)
    if not candidate_headings:
        aliases = [str(item).strip() for item in list(rule.get("aliases") or []) if str(item).strip()]
        return _headings_contain_aliases(headings, aliases)
    paragraph_map = {int(item.get("index") or 0): item for item in paragraphs}
    for heading in candidate_headings:
        heading_index = int(heading.get("paragraph_index") or 0)
        next_heading_index = None
        for sibling in candidate_headings:
            sibling_index = int(sibling.get("paragraph_index") or 0)
            if sibling_index > heading_index:
                next_heading_index = sibling_index
                break
        for index in range(heading_index + 1, next_heading_index or len(paragraphs)):
            paragraph = paragraph_map.get(index)
            if not paragraph:
                continue
            text = str(paragraph.get("text") or "").strip()
            if text and not paragraph.get("heading_level"):
                return True
    return False


def _find_docx_body_start_word_section_index(parsed: dict[str, Any]) -> int | None:
    headings = list(parsed.get("headings") or [])
    paragraphs = list(parsed.get("paragraphs") or [])
    if not paragraphs:
        return None

    preface_aliases = ["摘要", "关键词", "关键字", "目录", "引言", "绪论"]
    ending_aliases = ["参考文献", "致谢"]
    start_index = None
    end_index = None

    for heading in headings:
        text = str(heading.get("text") or "").strip()
        paragraph_index = heading.get("paragraph_index")
        if paragraph_index is None:
            continue
        if start_index is None and any(alias in text for alias in preface_aliases):
            start_index = int(paragraph_index)
        if any(alias in text for alias in ending_aliases):
            end_index = int(paragraph_index)
            break

    candidate_headings: list[dict[str, Any]] = []
    for heading in headings:
        paragraph_index = heading.get("paragraph_index")
        level = int(heading.get("level") or 0)
        if paragraph_index is None or level != 1:
            continue
        paragraph_index = int(paragraph_index)
        if start_index is not None and paragraph_index <= start_index:
            continue
        if end_index is not None and paragraph_index >= end_index:
            continue
        candidate_headings.append(heading)

    if not candidate_headings:
        return None

    paragraph_map = {int(item.get("index") or 0): item for item in paragraphs}
    for heading in candidate_headings:
        heading_index = int(heading.get("paragraph_index") or 0)
        next_heading_index = None
        for sibling in candidate_headings:
            sibling_index = int(sibling.get("paragraph_index") or 0)
            if sibling_index > heading_index:
                next_heading_index = sibling_index
                break
        for index in range(heading_index + 1, next_heading_index or len(paragraphs)):
            paragraph = paragraph_map.get(index)
            if not paragraph:
                continue
            text = str(paragraph.get("text") or "").strip()
            if text and not paragraph.get("heading_level"):
                word_section_index = paragraph.get("word_section_index")
                if isinstance(word_section_index, int):
                    return word_section_index
                return 0
    return None


def _check_docx_structure(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    headings = list(parsed.get("headings") or [])
    text = str(parsed.get("text") or "")
    if not _contains_any(text, ["摘要"]):
        issues.append(
            RuleIssue(
                code="structure.abstract_missing",
                title="缺少摘要",
                severity="high",
                category="structure",
                message="文档中未识别到'摘要'部分。",
                evidence="未找到标题或段落'摘要'",
                location={"section": "abstract"},
                suggestion="补充中文摘要并按模板放在前置部分。",
            )
        )
    if not _contains_any(text, ["Abstract", "ABSTRACT"]):
        issues.append(
            RuleIssue(
                code="structure.en_abstract_missing",
                title="缺少英文摘要",
                severity="high",
                category="structure",
                message="文档中未识别到英文摘要（Abstract）。",
                evidence="未找到 Abstract 标题",
                location={"section": "en_abstract"},
                suggestion="补充英文摘要（Abstract）并按模板放在前置部分。",
                parser_confidence="high",
            )
        )
    if not _contains_any(text, ["关键词", "关键字"]):
        issues.append(
            RuleIssue(
                code="structure.keywords_missing",
                title="缺少关键词",
                severity="medium",
                category="structure",
                message="文档中未识别到'关键词/关键字'部分。",
                evidence="未找到关键词字段",
                location={"section": "keywords"},
                suggestion="按模板添加关键词字段。",
            )
        )
    if not _contains_any(text, ["Keywords", "Key words"]):
        issues.append(
            RuleIssue(
                code="structure.en_keywords_missing",
                title="缺少英文关键词",
                severity="medium",
                category="structure",
                message="文档中未识别到英文关键词（Keywords/Key words）。",
                evidence="未找到 Keywords 字段",
                location={"section": "en_keywords"},
                suggestion="按模板补充英文关键词（Keywords）。",
                parser_confidence="high",
            )
        )
    if not _contains_any(text, ["参考文献"]):
        issues.append(
            RuleIssue(
                code="structure.references_missing",
                title="缺少参考文献",
                severity="high",
                category="structure",
                message="文档中未识别到'参考文献'部分。",
                evidence="未找到参考文献标题",
                location={"section": "references"},
                suggestion="补充参考文献章节并统一编号。",
            )
        )
    prev_level = 0
    for item in headings:
        level = int(item.get("level") or 0)
        if prev_level and level > prev_level + 1:
            issues.append(
                RuleIssue(
                    code="structure.heading_jump",
                    title="标题层级跳变",
                    severity="medium",
                    category="structure",
                    message=f"标题层级从 {prev_level} 级直接跳到 {level} 级。",
                    evidence=str(item.get("text") or ""),
                    location={
                        **_issue_location_from_paragraph(
                            next(
                                (
                                    paragraph for paragraph in list(parsed.get("paragraphs") or [])
                                    if paragraph.get("index") == item.get("paragraph_index")
                                ),
                                None,
                            )
                        ),
                        "heading_level": level,
                    },
                    suggestion="检查标题层级定义，避免跳级。",
                )
            )
            break
        prev_level = level or prev_level
    figure_titles = [item for item in list(parsed.get("figure_titles") or []) if item]
    if not figure_titles and _contains_any(text, ["图1", "图 1", "figure"]):
        issues.append(
            RuleIssue(
                code="structure.figure_caption_missing",
                title="图题可能缺失",
                severity="medium",
                category="structure",
                message="文中出现图示痕迹，但未识别到标准图题。",
                evidence="检测到图相关文本但未提取到图题",
                location={"section": "figure"},
                suggestion="检查图题是否按模板书写，例如'图 1 标题'。",
            )
        )
    return issues


def _check_pdf_structure(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    text = str(parsed.get("text") or "")
    if not _contains_any(text, ["摘要"]):
        issues.append(
            RuleIssue(
                code="structure.abstract_missing",
                title="缺少摘要",
                severity="high",
                category="structure",
                message="PDF 文本中未识别到'摘要'部分。",
                evidence="未找到标题或段落'摘要'",
                location={"section": "abstract"},
                suggestion="核对 PDF 是否包含中文摘要，或改传 Word 文档以做更完整校验。",
            )
        )
    if not _contains_any(text, ["关键词", "关键字"]):
        issues.append(
            RuleIssue(
                code="structure.keywords_missing",
                title="缺少关键词",
                severity="medium",
                category="structure",
                message="PDF 文本中未识别到'关键词/关键字'部分。",
                evidence="未找到关键词字段",
                location={"section": "keywords"},
                suggestion="补充关键词字段，或检查 PDF 文本是否可正确抽取。",
            )
        )
    if not _contains_any(text, ["参考文献"]):
        issues.append(
            RuleIssue(
                code="structure.references_missing",
                title="缺少参考文献",
                severity="high",
                category="structure",
                message="PDF 文本中未识别到'参考文献'部分。",
                evidence="未找到参考文献标题",
                location={"section": "references"},
                suggestion="补充参考文献章节，或检查 PDF 文本抽取结果。",
            )
        )
    return issues


def _check_docx_style(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    headings = list(parsed.get("headings") or [])
    paragraphs = list(parsed.get("paragraphs") or [])
    page = dict(parsed.get("page_layout") or {})

    if page:
        for margin_key in ("top_margin_cm", "bottom_margin_cm", "left_margin_cm", "right_margin_cm"):
            value = page.get(margin_key)
            if isinstance(value, (int, float)) and not (1.5 <= float(value) <= 4.0):
                issues.append(
                    RuleIssue(
                        code="style.margin_outlier",
                        title="页边距疑似异常",
                        severity="medium",
                        category="style",
                        message=f"{margin_key}={value}cm，超出常见论文模板范围。",
                        evidence=f"{margin_key}={value}",
                        location={"page_layout": margin_key},
                        suggestion="核对页边距设置是否符合模板要求。",
                    )
                )
                break
    for heading in headings[:5]:
        font_size = heading.get("font_size_pt")
        if font_size is not None and float(font_size) < 12:
            issues.append(
                RuleIssue(
                    code="style.heading_font_size_small",
                    title="标题字号偏小",
                    severity="medium",
                    category="style",
                    message="识别到标题字号小于常见论文模板要求。",
                    evidence=f"{heading.get('text')}: {font_size}pt",
                    location=_issue_location_from_paragraph(
                        next(
                            (
                                paragraph for paragraph in list(parsed.get("paragraphs") or [])
                                if paragraph.get("index") == heading.get("paragraph_index")
                            ),
                            None,
                        )
                    ),
                    suggestion="检查标题字号和样式配置。",
                )
            )
            break
    body_candidates = _body_paragraph_candidates(parsed)
    for paragraph in body_candidates[:10]:
        line_spacing = paragraph.get("line_spacing")
        if isinstance(line_spacing, (int, float)) and float(line_spacing) < 1.15:
            issues.append(
                RuleIssue(
                    code="style.line_spacing_small",
                    title="正文行距偏小",
                    severity="low",
                    category="style",
                    message="识别到正文行距偏小，可能不符合模板要求。",
                    evidence=f"段落 {paragraph.get('index')}: line_spacing={line_spacing}",
                    location=_issue_location_from_paragraph(paragraph),
                    suggestion="检查正文行距是否应为 1.5 倍或固定值。",
                )
            )
            break
    for paragraph in body_candidates:
        if _is_front_matter_paragraph(paragraph):
            continue
        indent = paragraph.get("first_line_indent_pt")
        if isinstance(indent, (int, float)) and float(indent) < 12:
            issues.append(
                RuleIssue(
                    code="style.paragraph_indent_missing",
                    title="正文首行缩进不足",
                    severity="low",
                    category="style",
                    message="识别到正文段落首行缩进小于常见 2 字符要求。",
                    evidence=f"段落 {paragraph.get('index')}: first_line_indent_pt={indent}",
                    location=_issue_location_from_paragraph(paragraph),
                    suggestion="将中文正文段落统一设置为首行缩进 2 字符。",
                    parser_confidence="medium",
                )
            )
            break
    # Check for inconsistent fonts in body paragraphs
    font_names: set[str] = set()
    for paragraph in body_candidates[:30]:
        fn = paragraph.get("font_name_resolved") or paragraph.get("font_name") or ""
        if fn:
            font_names.add(str(fn).strip())
    if len(font_names) > 2:
        issues.append(
            RuleIssue(
                code="style.body_font_inconsistent",
                title="正文字体不一致",
                severity="medium",
                category="style",
                message=f"正文中检测到 {len(font_names)} 种不同字体：{', '.join(sorted(font_names))}。",
                evidence=f"字体列表: {', '.join(sorted(font_names))}",
                location={"display_text": "正文区域", "scope": "body"},
                suggestion="将正文统一为模板规定的字体（中文宋体，英文 Times New Roman）。",
                actual={"fonts": sorted(font_names)},
                parser_confidence="medium",
            )
        )
    # Check for consecutive blank paragraphs or excessive empty lines
    blank_count = 0
    consecutive_blanks: list[int] = []
    for paragraph in paragraphs:
        text = str(paragraph.get("text") or "").strip()
        if not text and not paragraph.get("heading_level"):
            blank_count += 1
        else:
            if blank_count >= 2:
                consecutive_blanks.append(blank_count)
            blank_count = 0
    if consecutive_blanks:
        issues.append(
            RuleIssue(
                code="style.excessive_blank_paragraphs",
                title="存在多余空行",
                severity="low",
                category="style",
                message=f"正文中检测到 {len(consecutive_blanks)} 处连续空段落（最多连续 {max(consecutive_blanks)} 个），可能为排版异常。",
                evidence=f"连续空段落数: {consecutive_blanks[:5]}",
                location={"display_text": "正文区域", "scope": "body"},
                suggestion="检查并删除多余空行，正文段落间不应有空白段落。",
                parser_confidence="high",
            )
        )
    return issues


def _check_docx_page_setup(
    parsed: dict[str, Any],
    *,
    template: dict[str, Any],
    rules: dict[str, Any],
) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    page = dict(parsed.get("page_layout") or {})
    template_id = str(template.get("template_id") or DEFAULT_TEMPLATE_ID)
    size_rule = dict(rules.get("page_size_cm") or {})
    tolerance = float(size_rule.get("tolerance") or 0.2)
    expected_width = size_rule.get("width")
    expected_height = size_rule.get("height")
    actual_width = page.get("page_width_cm")
    actual_height = page.get("page_height_cm")
    if (
        isinstance(expected_width, (int, float))
        and isinstance(expected_height, (int, float))
        and isinstance(actual_width, (int, float))
        and isinstance(actual_height, (int, float))
        and (
            abs(float(actual_width) - float(expected_width)) > tolerance
            or abs(float(actual_height) - float(expected_height)) > tolerance
        )
    ):
        issues.append(
            RuleIssue(
                code="template.page_size_mismatch",
                title="纸张大小与模板不一致",
                severity="medium",
                category="template",
                message=f"页面大小 {actual_width}cm x {actual_height}cm 与模板 A4 尺寸不一致。",
                evidence=f"page_size_cm: actual=({actual_width}, {actual_height}), expected=({expected_width}, {expected_height})",
                location={"page_layout": "page_size", "template_id": template_id, "display_text": "页面设置"},
                suggestion="将纸张大小设置为 A4（21.0cm x 29.7cm）。",
                expected={"page_width_cm": expected_width, "page_height_cm": expected_height},
                actual={"page_width_cm": actual_width, "page_height_cm": actual_height},
                parser_confidence="high",
            )
        )

    expected_orientation = str(rules.get("page_orientation") or "").strip()
    actual_orientation = str(page.get("orientation") or "").strip()
    if expected_orientation and actual_orientation and actual_orientation != expected_orientation:
        issues.append(
            RuleIssue(
                code="template.page_orientation_mismatch",
                title="页面方向与模板不一致",
                severity="medium",
                category="template",
                message=f"页面方向为 {actual_orientation}，模板要求 {expected_orientation}。",
                evidence=f"orientation: actual={actual_orientation}, expected={expected_orientation}",
                location={"page_layout": "orientation", "template_id": template_id, "display_text": "页面方向"},
                suggestion="将论文主体页面方向设置为纵向。",
                expected={"orientation": expected_orientation},
                actual={"orientation": actual_orientation},
                parser_confidence="high",
            )
        )

    gutter_rule = dict(rules.get("gutter_cm") or {})
    expected_gutter = gutter_rule.get("value")
    actual_gutter = page.get("gutter_cm")
    gutter_tolerance = float(gutter_rule.get("tolerance") or 0.1)
    if (
        isinstance(expected_gutter, (int, float))
        and isinstance(actual_gutter, (int, float))
        and abs(float(actual_gutter) - float(expected_gutter)) > gutter_tolerance
    ):
        issues.append(
            RuleIssue(
                code="template.gutter_mismatch",
                title="装订线设置与模板不一致",
                severity="low",
                category="template",
                message=f"装订线为 {actual_gutter}cm，模板要求 {expected_gutter}cm。",
                evidence=f"gutter_cm: actual={actual_gutter}, expected={expected_gutter}",
                location={"page_layout": "gutter", "template_id": template_id, "display_text": "装订线设置"},
                suggestion="按学校模板调整装订线设置。",
                expected={"gutter_cm": expected_gutter},
                actual={"gutter_cm": actual_gutter},
                parser_confidence="high",
            )
        )

    header_footer_rule = dict(rules.get("header_footer") or {})
    hf_tolerance = float(header_footer_rule.get("tolerance") or 0.2)
    mismatches: dict[str, dict[str, Any]] = {}
    for key in ("header_distance_cm", "footer_distance_cm"):
        expected = header_footer_rule.get(key)
        actual = page.get(key)
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            if abs(float(actual) - float(expected)) > hf_tolerance:
                mismatches[key] = {"expected": expected, "actual": actual}
    if mismatches:
        issues.append(
            RuleIssue(
                code="template.header_footer_mismatch",
                title="页眉页脚距离与模板不一致",
                severity="low",
                category="template",
                message="识别到页眉或页脚距离与学校模板设置不一致。",
                evidence=", ".join(f"{k}: actual={v['actual']}, expected={v['expected']}" for k, v in mismatches.items()),
                location={"page_layout": "header_footer", "template_id": template_id, "display_text": "页眉页脚设置"},
                suggestion="按学校模板统一页眉距边界、页脚距边界设置。",
                expected={key: value["expected"] for key, value in mismatches.items()},
                actual={key: value["actual"] for key, value in mismatches.items()},
                parser_confidence="high",
            )
        )
    # Check header/footer text content against template requirements
    header_footer_content_rule = dict(rules.get("header_footer") or {})
    expected_header = str(header_footer_content_rule.get("expected_header_text") or "").strip()
    cover_no_hf = bool(header_footer_content_rule.get("cover_no_header_footer"))
    sections = list(parsed.get("sections") or [])
    body_start_word_section_index = _find_docx_body_start_word_section_index(parsed)
    header_sections = (
        sections[body_start_word_section_index:]
        if isinstance(body_start_word_section_index, int) and body_start_word_section_index < len(sections)
        else []
    )
    header_texts = [str(sec.get("header_text") or "").strip() for sec in header_sections]
    footer_texts = [str(sec.get("footer_text") or "").strip() for sec in sections]
    if expected_header and header_texts:
        any_header_match = any(expected_header in ht for ht in header_texts if ht)
        if any(ht for ht in header_texts) and not any_header_match:
            issues.append(
                RuleIssue(
                    code="template.header_content_mismatch",
                    title="页眉内容与模板要求不一致",
                    severity="medium",
                    category="template",
                    message=f"模板要求正文开始后的页眉包含 {expected_header}，但未在正文范围内的任何节页眉中检测到。",
                    evidence=f"正文范围内检测到的页眉文本: {[ht[:60] for ht in header_texts if ht][:5]}",
                    location={"display_text": "正文后的页眉区域", "scope": "headers_after_body"},
                    suggestion=f"在页眉中添加 {expected_header}。",
                    expected={"header_text": expected_header},
                    actual={"header_texts": [ht[:80] for ht in header_texts if ht][:5]},
                    parser_confidence="high",
                )
            )
    if cover_no_hf and sections:
        first_section = sections[0]
        first_header = str(first_section.get("header_text") or "").strip()
        first_footer = str(first_section.get("footer_text") or "").strip()
        if first_header or first_footer:
            issues.append(
                RuleIssue(
                    code="template.cover_has_header_footer",
                    title="封面不应包含页眉页脚",
                    severity="medium",
                    category="template",
                    message="封面通常不应有页眉和页脚。",
                    evidence=f"封面页眉: {repr(first_header[:60])}, 页脚: {repr(first_footer[:60])}",
                    location={"display_text": "封面区域", "section_index": 0},
                    suggestion="在 Word 中为封面设置独立的节，取消首页页眉页脚。",
                    parser_confidence="high",
                )
            )
    return issues


def _check_template_rules(
    parsed: dict[str, Any],
    *,
    template: dict[str, Any],
    document_type: str,
) -> list[RuleIssue]:
    template_id = str(template.get("template_id") or DEFAULT_TEMPLATE_ID)
    if template_id == DEFAULT_TEMPLATE_ID:
        return []
    if document_type == "docx":
        rules = dict(template.get("docx_rules") or {})
    elif document_type == "pdf":
        rules = dict(template.get("pdf_rules") or template.get("docx_rules") or {})
    elif document_type == "tex":
        rules = dict(template.get("tex_rules") or {})
    else:
        return []

    issues: list[RuleIssue] = []
    for section in list(rules.get("required_sections") or []):
        section_rule = _normalize_required_section_rule(section)
        section_name = str(section_rule.get("label") or "")
        if section_name and not _required_section_present(parsed, section_rule, document_type=document_type):
            issues.append(
                RuleIssue(
                    code="template.required_section_missing",
                    title=f"模板要求章节缺失：{section_name}",
                    severity=str(section_rule.get("severity") or "medium"),
                    category="template",
                    message=f"按 {template.get('name')} 规则未识别到'{section_name}'。",
                    evidence=f"未找到模板章节：{section_name}",
                    location={
                        "section": section_name,
                        "template_id": template_id,
                        "display_text": f"模板要求存在《{section_name}》章节",
                    },
                    suggestion=f"按学校模板补充或核对'{section_name}'章节。",
                )
            )

    if document_type != "docx":
        return issues

    issues.extend(_check_docx_page_setup(parsed, template=template, rules=rules))

    page_rules = dict(rules.get("page_margin_cm") or {})
    page = dict(parsed.get("page_layout") or {})
    tolerance = float(page_rules.get("tolerance") or 0.2)
    margin_map = {
        "top": "top_margin_cm",
        "bottom": "bottom_margin_cm",
        "left": "left_margin_cm",
        "right": "right_margin_cm",
    }
    for rule_key, parsed_key in margin_map.items():
        expected = page_rules.get(rule_key)
        actual = page.get(parsed_key)
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            if abs(float(actual) - float(expected)) > tolerance:
                issues.append(
                    RuleIssue(
                        code="template.margin_mismatch",
                        title="页边距与学校模板不一致",
                        severity="medium",
                        category="template",
                        message=f"{parsed_key}={actual}cm，与模板建议 {expected}cm 不一致。",
                        evidence=f"{parsed_key}: actual={actual}, expected={expected}",
                        location={"page_layout": parsed_key, "template_id": template_id, "display_text": "页面版式设置"},
                        suggestion="按学校模板重新设置页面边距。",
                        expected={parsed_key: expected},
                        actual={parsed_key: actual},
                        parser_confidence="high",
                    )
                )
                break

    body_font = dict(rules.get("body_font") or {})
    body_candidates = _body_paragraph_candidates(parsed)
    expected_names = {
        str(body_font.get("zh") or "").lower(),
        str(body_font.get("en") or "").lower(),
    } - {""}
    expected_size = body_font.get("size_pt")
    font_mismatch_samples: list[dict[str, Any]] = []
    font_mismatch_count = 0
    unresolved_font_count = 0
    for paragraph in body_candidates:
        actual_name = str(
            paragraph.get("font_name_resolved") or paragraph.get("font_name") or ""
        ).lower()
        actual_size = paragraph.get("font_size_resolved") or paragraph.get("font_size_pt")
        # Font inherited from styles — skip name check when unresolved
        if actual_name:
            name_mismatch = actual_name not in expected_names
        else:
            name_mismatch = False
            unresolved_font_count += 1
        size_mismatch = (
            isinstance(expected_size, (int, float))
            and isinstance(actual_size, (int, float))
            and abs(float(actual_size) - float(expected_size)) > 0.2
        )
        if name_mismatch or size_mismatch:
            font_mismatch_count += 1
            if len(font_mismatch_samples) < 5:
                font_mismatch_samples.append({
                    "paragraph_index": paragraph.get("index"),
                    "display_text": _issue_location_from_paragraph(paragraph).get("display_text"),
                    "section_title": paragraph.get("section_title"),
                    "font_name": actual_name or "(样式继承-未识别)",
                    "font_size_pt": actual_size,
                    "text": _build_paragraph_evidence_excerpt(paragraph),
                })
    if font_mismatch_count:
        first_sample = font_mismatch_samples[0] if font_mismatch_samples else {}
        sample_text = "；".join(
            f"{item.get('display_text')}: “{item.get('text')}” (font={item.get('font_name')}, size={item.get('font_size_pt')})"
            for item in font_mismatch_samples
        )
        issues.append(
            RuleIssue(
                code="template.body_font_mismatch",
                title="正文字体或字号与学校模板不一致",
                severity="medium",
                category="template",
                message=f"已扫描 {len(body_candidates)} 个正文段落，其中 {font_mismatch_count} 个字体/字号与模板不一致" + (f"，{unresolved_font_count} 个段落字体由样式继承无法识别（不计入差异）" if unresolved_font_count > 0 else ""),
                evidence=f"不一致段落 {font_mismatch_count}/{len(body_candidates)}" + (f"，{unresolved_font_count} 个为样式继承" if unresolved_font_count > 0 else "") + f"。示例：{sample_text}",
                location={
                    "section_title": first_sample.get("section_title"),
                    "paragraph_index": first_sample.get("paragraph_index"),
                    "template_id": template_id,
                    "display_text": f"正文样式汇总（首个示例：{first_sample.get('display_text') or '正文段落'}）",
                },
                suggestion="按学校模板统一全文正文的中文字体、英文字体和字号；优先修改正文样式定义，再抽查样例段落。",
                expected={"zh_font": body_font.get("zh"), "en_font": body_font.get("en"), "font_size_pt": body_font.get("size_pt")},
                actual={"mismatch_count": font_mismatch_count, "checked_count": len(body_candidates), "samples": font_mismatch_samples},
                source_clause_ids=["cqupt_2022_body_font"],
                parser_confidence="medium",
            )
        )

    expected_spacing = rules.get("line_spacing")
    if isinstance(expected_spacing, (int, float)):
        for paragraph in body_candidates:
            actual_spacing = paragraph.get("line_spacing")
            if (
                isinstance(actual_spacing, (int, float))
                and float(actual_spacing) <= 5
                and abs(float(actual_spacing) - float(expected_spacing)) > 0.1
            ):
                issues.append(
                    RuleIssue(
                        code="template.line_spacing_mismatch",
                        title="正文行距与学校模板不一致",
                        severity="low",
                        category="template",
                        message=f"正文行距 {actual_spacing} 与模板建议 {expected_spacing} 不一致。",
                        evidence=f"段落 {paragraph.get('index')}: line_spacing={actual_spacing}",
                        location={**_issue_location_from_paragraph(paragraph), "template_id": template_id},
                        suggestion="按学校模板统一正文行距。",
                        expected={"line_spacing": expected_spacing},
                        actual={"line_spacing": actual_spacing},
                        source_clause_ids=["cqupt_2022_body_line_spacing"],
                        parser_confidence="medium",
                    )
                )
                break

    return issues


def _check_tex_structure(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    commands = dict(parsed.get("commands") or {})
    sections = list(parsed.get("sections") or [])
    text = str(parsed.get("text") or "")

    if not commands.get("title"):
        issues.append(
            RuleIssue(
                code="tex.title_missing",
                title="缺少标题命令",
                severity="high",
                category="structure",
                message="未识别到 \\title{...}。",
                evidence="缺少 \\title",
                location={"command": "title"},
                suggestion="补充 LaTeX 标题命令。",
            )
        )
    if not commands.get("author"):
        issues.append(
            RuleIssue(
                code="tex.author_missing",
                title="缺少作者命令",
                severity="medium",
                category="structure",
                message="未识别到 \\author{...}。",
                evidence="缺少 \\author",
                location={"command": "author"},
                suggestion="补充作者信息。",
            )
        )
    if not _contains_any(text, ["摘要"]) and not commands.get("abstract"):
        issues.append(
            RuleIssue(
                code="tex.abstract_missing",
                title="缺少摘要",
                severity="high",
                category="structure",
                message="未识别到摘要环境或摘要标题。",
                evidence="缺少 abstract / 摘要",
                location={"section": "abstract"},
                suggestion="补充摘要环境或章节。",
            )
        )
    if not _contains_any(text, ["参考文献"]) and not commands.get("bibliography"):
        issues.append(
            RuleIssue(
                code="tex.references_missing",
                title="缺少参考文献",
                severity="high",
                category="structure",
                message="未识别到参考文献命令或章节。",
                evidence="缺少 bibliography / references",
                location={"section": "references"},
                suggestion="补充参考文献环境并统一引用。",
            )
        )
    prev_level = 0
    for item in sections:
        level = _SECTION_CMD_LEVEL.get(str(item.get("command") or ""), 0)
        if prev_level and level > prev_level + 1:
            issues.append(
                RuleIssue(
                    code="tex.section_jump",
                    title="章节层级跳变",
                    severity="medium",
                    category="structure",
                message="LaTeX 章节层级存在跳级。",
                evidence=str(item.get("title") or ""),
                location=_issue_location_from_tex(item),
                suggestion="检查 section/subsection/subsubsection 层级。",
            )
        )
            break
        prev_level = level or prev_level
    if parsed.get("figure_count", 0) > 0 and not parsed.get("figure_titles"):
        issues.append(
            RuleIssue(
                code="tex.figure_caption_missing",
                title="图题可能缺失",
                severity="medium",
                category="structure",
                message="检测到 figure 环境，但未识别到 caption。",
                evidence="figure without caption",
                location={"environment": "figure", "display_text": "figure 环境附近"},
                suggestion="为图表补充 \\caption{}。",
            )
        )
    return issues


def _check_front_matter_rules(
    parsed: dict[str, Any],
    *,
    template: dict[str, Any],
    document_type: str,
) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    if document_type not in {"docx", "pdf", "tex"}:
        return issues
    rules = dict(template.get(f"{document_type}_rules") or template.get("docx_rules") or {})
    keyword_rule = dict(rules.get("abstract_keywords") or {})
    min_count = int(keyword_rule.get("min_count") or 3)
    max_count = int(keyword_rule.get("max_count") or 5)
    allowed_separators = [str(item) for item in list(keyword_rule.get("separators") or ["；", ";"]) if str(item)]
    text = str(parsed.get("text") or "")

    keyword_match = re.search(r"(?:关键词|关键字)\s*[:：]\s*([^\n]+)", text)
    if keyword_match:
        raw_keywords = keyword_match.group(1).strip()
        keywords = [item.strip() for item in re.split(r"[；;，,、\s]+", raw_keywords) if item.strip()]
        if not (min_count <= len(keywords) <= max_count):
            issues.append(
                RuleIssue(
                    code="abstract.keyword_count_out_of_range",
                    title="中文关键词数量不符合要求",
                    severity="medium",
                    category="structure",
                    message=f"识别到 {len(keywords)} 个中文关键词，模板建议 {min_count}-{max_count} 个。",
                    evidence=keyword_match.group(0),
                    location={"section": "keywords", "display_text": "中文关键词"},
                    suggestion=f"将关键词数量调整为 {min_count}-{max_count} 个。",
                    expected={"min_count": min_count, "max_count": max_count},
                    actual={"count": len(keywords), "keywords": keywords},
                    parser_confidence="high",
                )
            )
        if allowed_separators and len(keywords) > 1 and not any(separator in raw_keywords for separator in allowed_separators):
            issues.append(
                RuleIssue(
                    code="abstract.keyword_separator_mismatch",
                    title="中文关键词分隔符与模板不一致",
                    severity="low",
                    category="structure",
                    message="关键词之间未使用模板建议的分隔符。",
                    evidence=keyword_match.group(0),
                    location={"section": "keywords", "display_text": "中文关键词"},
                    suggestion=f"使用 {' 或 '.join(allowed_separators)} 分隔关键词。",
                    expected={"separators": allowed_separators},
                    actual={"text": raw_keywords},
                    parser_confidence="high",
                )
            )

    if re.search(r"(?:摘要|ABSTRACT)[\s\S]{0,600}(?:图\d+|表\d+|\[\d+\]|（\d+(?:[-.]\d+)*）)", text, flags=re.I):
        issues.append(
            RuleIssue(
                code="abstract.contains_figure_formula_or_citation",
                title="摘要中疑似包含图表、公式或参考文献编号",
                severity="low",
                category="structure",
                message="摘要区域内识别到图表、公式或参考文献编号痕迹。",
                evidence="摘要附近出现图表/公式/引用编号",
                location={"section": "abstract", "display_text": "摘要"},
                suggestion="摘要通常应避免出现图表、公式和参考文献编号。",
                parser_confidence="medium",
            )
        )
    return issues


def _check_toc_rules(parsed: dict[str, Any], *, template: dict[str, Any]) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    rules = dict(template.get("docx_rules") or {})
    required_entries = [str(item).strip() for item in list(rules.get("toc_required_entries") or []) if str(item).strip()]
    if not required_entries:
        return issues
    toc_entries = list(parsed.get("toc_entries") or [])
    text = str(parsed.get("text") or "")
    has_toc = bool(toc_entries) or "目录" in text
    if not has_toc:
        return issues
    toc_text = "\n".join(str(item.get("title") or "") for item in toc_entries) if toc_entries else _toc_text_window(text)
    normalized_toc_text = _normalize_loose_text(toc_text)
    missing = [entry for entry in required_entries if _normalize_loose_text(entry) not in normalized_toc_text]
    if missing:
        issues.append(
            RuleIssue(
                code="toc.required_entry_missing",
                title="目录缺少模板要求条目",
                severity="medium",
                category="structure",
                message=f"目录中未识别到条目：{', '.join(missing[:8])}。",
                evidence=f"目录条目样例：{toc_text[:200]}",
                location={"section": "toc", "display_text": "目录"},
                suggestion="更新自动目录，确保摘要、图目录、表目录、参考文献、致谢等模板要求条目在目录中出现。",
                expected={"required_entries": required_entries},
                actual={"missing_entries": missing},
                parser_confidence="medium" if not toc_entries else "high",
            )
        )
    return issues


def _check_text_norms(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    text = str(parsed.get("text") or "")
    paragraphs = list(parsed.get("paragraphs") or [])
    seen_fullwidth = re.search(r"[Ａ-Ｚａ-ｚ０-９]", text)
    if seen_fullwidth:
        fullwidth_hit = _build_text_hit_location(parsed, seen_fullwidth.start())
        fullwidth_evidence = _build_text_hit_evidence(parsed, seen_fullwidth.start(), seen_fullwidth.end(), default_text=text)
        issues.append(
            RuleIssue(
                code="text.fullwidth_ascii",
                title="全半角字符混用",
                severity="low",
                category="text",
                message="检测到全角英文或数字字符。",
                evidence=fullwidth_evidence,
                location=fullwidth_hit,
                suggestion="统一改为半角英文和数字。",
            )
        )
    double_space = re.search(r"[^\n]\s{2,}[^\n]", text)
    if double_space:
        matched_paragraph = _find_paragraph_by_offset(parsed, double_space.start())
        issues.append(
            RuleIssue(
                code="text.multiple_spaces",
                title="存在连续空格",
                severity="low",
                category="text",
                message="检测到连续空格。",
                evidence=double_space.group(0),
                location=(
                    _issue_location_from_paragraph(matched_paragraph)
                    if str(parsed.get("kind") or "") == "docx"
                    else {"offset": double_space.start(), "display_text": "文档文本附近"}
                ),
                suggestion="清理多余空格，保持排版一致。",
            )
        )
    mixed_punctuation_hit = _find_mixed_punctuation_hit(parsed)
    if mixed_punctuation_hit:
        hit_count = _count_mixed_punctuation_hits(parsed)
        issues.append(
            RuleIssue(
                code="text.mixed_punctuation",
                title="中英文标点混用",
                severity="medium",
                category="text",
                message=f"检测到全文约 {hit_count} 处中英文标点混用，如中文语境中使用英文括号/逗号，或英文语境中使用中文标点。",
                evidence=str(mixed_punctuation_hit.get("evidence") or ""),
                location=dict(mixed_punctuation_hit.get("location") or {"scope": "document"}),
                suggestion="统一标点风格：中文正文使用全角标点，英文使用半角标点。",
                actual={"estimated_total_hits": hit_count},
                parser_confidence="medium",
            )
        )
    for paragraph in paragraphs[:30]:
        content = str(paragraph.get("text") or "")
        if paragraph.get("heading_level") and content.endswith(tuple(_ZH_PUNCT + _EN_PUNCT)):
            issues.append(
                RuleIssue(
                    code="text.heading_trailing_punct",
                    title="标题末尾含标点",
                    severity="low",
                    category="text",
                message="标题末尾通常不应保留句末标点。",
                evidence=content,
                location=_issue_location_from_paragraph(paragraph),
                suggestion="移除标题末尾句号、逗号、冒号等标点。",
            )
        )
            break
    # Check Chinese-English spacing: Chinese char followed by ASCII letter/digit without space
    cn_en_no_space = re.findall(r"[一-鿿][A-Za-z0-9]|[一-鿿]\(", text)
    if cn_en_no_space:
        evidence_text = text[:4000]
        first_hit = re.search(r"[一-鿿][A-Za-z0-9(]", text)
        offset = first_hit.start() if first_hit else 0
        issues.append(
            RuleIssue(
                code="text.cn_en_space_missing",
                title="中英文之间缺少空格",
                severity="low",
                category="text",
                message=f"检测到 {len(cn_en_no_space)} 处中文与英文/数字之间缺少空格，可能影响排版美观。",
                evidence=_build_evidence_excerpt(text, offset, offset + 4),
                location=_build_text_hit_location(parsed, offset),
                suggestion="在中英文之间添加半角空格以改善排版美观度。",
                parser_confidence="medium",
            )
        )
    return issues


def _run_docx_text_engines(parsed: dict[str, Any], *, file_name: str) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    issues.extend(_check_text_norms(parsed))
    issues.extend(_check_pycorrector(parsed))
    issues.extend(_check_macro_correct(parsed))
    issues.extend(_check_language_tool(parsed, file_name=file_name))
    issues.extend(_check_vale(parsed))
    return issues


def _check_language_tool(parsed: dict[str, Any], *, file_name: str) -> list[RuleIssue]:
    if not settings.paper_check_languagetool_enabled:
        return []
    base_url = str(settings.paper_check_languagetool_url or "").strip().rstrip("/")
    if not base_url:
        raise PaperReviewDependencyError("paper_check_languagetool_url 未配置")
    text = str(parsed.get("text") or "").strip()
    if not text:
        return []
    try:
        timeout = httpx.Timeout(float(settings.paper_check_languagetool_timeout_sec or 20))
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.post(
                f"{base_url}/v2/check",
                data={
                    "text": text[:12000],
                    "language": settings.paper_check_languagetool_language,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []
    issues: list[RuleIssue] = []
    for match in list(payload.get("matches") or [])[:20]:
        message = str(match.get("message") or "").strip()
        offset = int(match.get("offset") or 0)
        length = int(match.get("length") or 0)
        evidence = text[offset: offset + length] if length > 0 else text[offset: offset + 20]
        category_name = str(((match.get("rule") or {}).get("category") or {}).get("id") or "text").lower()
        matched_paragraph = _find_paragraph_by_offset(parsed, offset)
        issues.append(
                RuleIssue(
                    code=f"languagetool.{str((match.get('rule') or {}).get('id') or 'match').lower()}",
                    title="语言校对提示",
                    severity="low",
                    category="text" if category_name else "text",
                    message=message or "检测到可能的语言或标点问题。",
                    evidence=_build_text_hit_evidence(parsed, offset, offset + max(length, 1), default_text=text)[:120],
                    location=(
                        {
                            **_issue_location_from_paragraph(matched_paragraph),
                            "file": file_name,
                            "offset": offset,
                        "length": length,
                    }
                    if str(parsed.get("kind") or "") == "docx"
                    else {"file": file_name, "offset": offset, "length": length, "display_text": "文档文本附近"}
                ),
                    suggestion=_language_tool_suggestion(match),
                    engine="languagetool",
                    engine_rule_id=str((match.get("rule") or {}).get("id") or "match"),
                    confidence="medium",
                    parser_confidence="high",
                )
            )
    return issues


def _check_pycorrector(parsed: dict[str, Any]) -> list[RuleIssue]:
    if not settings.paper_check_pycorrector_enabled:
        return []

    body_paragraphs = [
        paragraph
        for paragraph in list(parsed.get("paragraphs") or [])
        if str(paragraph.get("text") or "").strip() and not paragraph.get("heading_level")
    ]
    if not body_paragraphs:
        return []

    chunk_limit = max(300, int(settings.paper_check_pycorrector_chunk_chars or 1200))
    timeout_sec = max(1.0, float(settings.paper_check_pycorrector_timeout_sec or settings.paper_check_engine_timeout_sec or 8))
    chunks = _build_pycorrector_chunks(body_paragraphs, chunk_limit=chunk_limit)
    if not chunks:
        return []

    try:
        chunk_results = asyncio.run(
            asyncio.wait_for(
                asyncio.to_thread(_run_pycorrector_on_chunks, chunks),
                timeout=timeout_sec,
            )
        )
    except PycorrectorUnavailableError as exc:
        raise PaperReviewDependencyError(f"pycorrector 不可用：{exc}") from exc
    except asyncio.TimeoutError:
        logger.warning("pycorrector timed out after %.1fs for %d chunks", timeout_sec, len(chunks))
        return []
    except Exception as exc:
        logger.warning("pycorrector failed: %s", exc)
        return []

    issues: list[RuleIssue] = []
    for paragraph, wrong, right, begin, end, entrypoint in chunk_results[:30]:
        text = str(paragraph.get("text") or "").strip()
        if not text or _should_skip_spelling_hit(text, wrong, right):
            continue
        evidence = _build_evidence_excerpt(text, begin, end)
        location = _issue_location_from_paragraph(paragraph)
        location["offset"] = begin
        issues.append(
            RuleIssue(
                code="pycorrector.spelling",
                title="疑似错别字",
                severity="medium",
                category="text",
                message=f"检测到疑似错别字：{wrong} -> {right}。",
                evidence=evidence,
                location=location,
                suggestion=f"将“{wrong}”改为“{right}”，并结合上下文复核。",
                engine="pycorrector",
                engine_rule_id=entrypoint,
                confidence="medium",
                parser_confidence="high",
                actual={"wrong": wrong, "right": right},
            )
        )
    return issues


def _build_pycorrector_chunks(
    paragraphs: list[dict[str, Any]],
    *,
    chunk_limit: int,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current_items: list[dict[str, Any]] = []
    current_length = 0

    def flush() -> None:
        nonlocal current_items, current_length
        if not current_items:
            return
        text_parts: list[str] = []
        offsets: list[dict[str, Any]] = []
        cursor = 0
        for item in current_items:
            paragraph_text = str(item.get("text") or "")
            text_parts.append(paragraph_text)
            offsets.append(
                {
                    "paragraph": item,
                    "start": cursor,
                    "end": cursor + len(paragraph_text),
                }
            )
            cursor += len(paragraph_text) + 1
        chunks.append({"text": "\n".join(text_parts), "offsets": offsets})
        current_items = []
        current_length = 0

    for paragraph in paragraphs:
        text = str(paragraph.get("text") or "").strip()
        if not text:
            continue
        projected = current_length + len(text) + (1 if current_items else 0)
        if current_items and projected > chunk_limit:
            flush()
        current_items.append(paragraph)
        current_length += len(text) + (1 if current_items[:-1] else 0)
    flush()
    return chunks


def _run_pycorrector_on_chunks(chunks: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str, str, int, int, str]]:
    results: list[tuple[dict[str, Any], str, str, int, int, str]] = []
    for chunk in chunks:
        text = str(chunk.get("text") or "")
        if not text.strip():
            continue
        corrected, entrypoint = run_pycorrector(text)
        for wrong, right, begin, end in normalize_pycorrector_errors(corrected):
            paragraph, local_begin, local_end = _map_chunk_offset_to_paragraph(chunk, begin, end)
            if paragraph is None:
                continue
            results.append((paragraph, wrong, right, local_begin, local_end, entrypoint))
    return results


def _map_chunk_offset_to_paragraph(
    chunk: dict[str, Any],
    begin: int,
    end: int,
) -> tuple[dict[str, Any] | None, int, int]:
    for item in list(chunk.get("offsets") or []):
        start = int(item.get("start") or 0)
        stop = int(item.get("end") or start)
        if start <= begin <= stop:
            paragraph = item.get("paragraph")
            local_begin = max(0, begin - start)
            local_end = max(local_begin + 1, min(stop, end) - start)
            return paragraph if isinstance(paragraph, dict) else None, local_begin, local_end
    return None, 0, 0


def _check_macro_correct(parsed: dict[str, Any]) -> list[RuleIssue]:
    if not settings.paper_check_macro_correct_enabled:
        return []
    paragraphs = list(parsed.get("paragraphs") or [])
    if not paragraphs:
        return []

    issues: list[RuleIssue] = []
    texts: list[str] = []
    paragraph_refs: list[dict[str, Any]] = []
    for paragraph in paragraphs:
        text = str(paragraph.get("text") or "").strip()
        if not text:
            continue
        texts.append(text)
        paragraph_refs.append(paragraph)

    if not texts:
        return []

    token_results = None
    token_entrypoint = ""
    punct_results = None
    punct_entrypoint = ""
    token_error: MacroCorrectUnavailableError | None = None
    punct_error: MacroCorrectUnavailableError | None = None

    try:
        token_results, token_entrypoint = run_macro_correct_token(texts)
    except MacroCorrectUnavailableError as exc:
        token_error = exc
    except Exception as exc:
        logger.warning("macro-correct token detector failed: %s", exc)

    try:
        punct_results, punct_entrypoint = run_macro_correct_punct(texts)
    except MacroCorrectUnavailableError as exc:
        punct_error = exc
    except Exception as exc:
        logger.warning("macro-correct punct detector failed: %s", exc)

    if token_results is None and punct_results is None:
        detail_parts = [str(err) for err in (token_error, punct_error) if err]
        raise PaperReviewDependencyError(f"macro-correct 不可用：{'; '.join(detail_parts) or 'no callable detector'}")

    combined_hits: dict[int, list[tuple[dict[str, Any], str, str]]] = {}
    for index, hit in _normalize_macro_correct_batch_hits(token_results):
        combined_hits.setdefault(index, []).append((hit, token_entrypoint or "macro_correct.token", "中文拼写建议"))
    for index, hit in _normalize_macro_correct_batch_hits(punct_results):
        combined_hits.setdefault(index, []).append((hit, punct_entrypoint or "macro_correct.punct", "中文标点建议"))

    for index, paragraph in enumerate(paragraph_refs):
        text = texts[index]
        for hit, entrypoint, title in combined_hits.get(index, [])[:10]:
            begin = int(hit.get("begin") or 0)
            end = int(hit.get("end") or begin + len(str(hit.get("wrong") or "")))
            wrong = str(hit.get("wrong") or "").strip()
            right = str(hit.get("right") or "").strip()
            if not wrong and not right:
                continue
            location = _issue_location_from_paragraph(paragraph)
            location["offset"] = begin
            issues.append(
                RuleIssue(
                    code=f"macro_correct.{str(hit.get('rule_id') or 'suggestion')}",
                    title=title,
                    severity="medium",
                    category="text",
                    message=str(hit.get("message") or f"检测到需要调整的表达：{wrong or _build_evidence_excerpt(text, begin, end)}。"),
                    evidence=_build_evidence_excerpt(text, begin, end),
                    location=location,
                    suggestion=str(hit.get("suggestion") or (f"建议改为“{right}”。" if right else "请结合上下文人工复核。")),
                    engine="macro_correct",
                    engine_rule_id=entrypoint,
                    confidence="medium",
                    parser_confidence="high",
                    actual={"wrong": wrong, "right": right},
                )
            )
    return issues


def _check_vale(parsed: dict[str, Any]) -> list[RuleIssue]:
    text = _build_vale_input_text(parsed)
    if not text.strip():
        return []
    vale_bin = str(settings.paper_check_vale_bin or "vale").strip() or "vale"
    config_dir = Path(str(settings.paper_check_vale_config_dir or "").strip() or "agent/tools/assets/vale")
    if not config_dir.is_absolute():
        config_dir = Path(__file__).resolve().parents[2] / config_dir
    config_path = config_dir / ".vale.ini"
    timeout_sec = float(settings.paper_check_vale_timeout_sec or settings.paper_check_engine_timeout_sec or 20)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as fp:
        fp.write(text)
        temp_path = fp.name
    try:
        completed = subprocess.run(
            [vale_bin, "--config", str(config_path), "--output", "JSON", temp_path],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if completed.returncode not in {0, 1}:
            raise PaperReviewDependencyError(f"Vale 执行失败：{completed.stderr.strip() or completed.stdout.strip()}")
        payload = json.loads(completed.stdout or "{}")
    finally:
        Path(temp_path).unlink(missing_ok=True)

    issues: list[RuleIssue] = []
    for entries in payload.values():
        for entry in list(entries or [])[:20]:
            line_no = int(entry.get("Line") or 1)
            rule_id = str(entry.get("Check") or "style")
            span = _vale_line_to_paragraph(parsed, line_no)
            if not span:
                continue
            paragraph, evidence = span
            issues.append(
                RuleIssue(
                    code=f"vale.{rule_id.lower()}",
                    title="写作规范建议",
                    severity="low",
                    category="writing",
                    message=str(entry.get("Message") or "检测到写作规范问题。"),
                    evidence=evidence,
                    location=_issue_location_from_paragraph(paragraph),
                    suggestion=str(entry.get("Message") or "请根据写作规范调整。"),
                    engine="vale",
                    engine_rule_id=rule_id,
                    confidence="medium",
                    parser_confidence="high",
                )
            )
    return issues


def _language_tool_suggestion(match: dict[str, Any]) -> str:
    replacements = [str(item.get("value") or "").strip() for item in list(match.get("replacements") or []) if item.get("value")]
    if replacements:
        return f"可优先参考替换建议：{', '.join(replacements[:3])}"
    return "请结合上下文人工复核该处表述。"


def _toc_text_window(text: str) -> str:
    content = str(text or "")
    index = content.find("目录")
    if index < 0:
        return content[:1200]
    return content[index:index + 2000]


def _body_paragraph_candidates(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    paragraphs = [
        item for item in list(parsed.get("paragraphs") or [])
        if str(item.get("text") or "").strip() and not item.get("heading_level")
    ]
    candidates = [
        item for item in paragraphs
        if _looks_like_body_paragraph(item)
    ]
    return candidates or paragraphs


def _looks_like_body_paragraph(paragraph: dict[str, Any]) -> bool:
    if _is_front_matter_paragraph(paragraph):
        return False
    section_title = str(paragraph.get("section_title") or "").strip()
    text = str(paragraph.get("text") or "").strip()
    if not section_title:
        return False
    if len(text) < 6 and not re.search(r"[\u4e00-\u9fff].*[\u4e00-\u9fff]", text):
        return False
    return True


def _is_front_matter_paragraph(paragraph: dict[str, Any]) -> bool:
    section_title = str(paragraph.get("section_title") or "")
    text = str(paragraph.get("text") or "")
    front_keywords = ("摘要", "abstract", "关键词", "keywords", "目录", "图目录", "表目录", "参考文献", "致谢")
    lowered = f"{section_title}\n{text}".lower()
    return any(keyword.lower() in lowered for keyword in front_keywords)


def _normalize_loose_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    loose = _normalize_loose_text(text)
    return any(keyword.lower() in lowered or _normalize_loose_text(keyword) in loose for keyword in keywords)


def _find_mixed_punctuation_hit(parsed: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(parsed.get("kind") or "")
    if kind == "docx":
        for paragraph in list(parsed.get("paragraphs") or []):
            text = str(paragraph.get("text") or "").strip()
            if not text:
                continue
            evidence = _extract_mixed_punctuation_evidence(text)
            if evidence:
                return {
                    "evidence": evidence,
                    "location": _issue_location_from_paragraph(paragraph),
                }
        return None

    if kind == "tex":
        for item in list(parsed.get("paragraphs") or []):
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            evidence = _extract_mixed_punctuation_evidence(text)
            if evidence:
                return {
                    "evidence": evidence,
                    "location": _issue_location_from_tex(item),
                }
        return None

    if kind == "pdf":
        for page in list(parsed.get("pages") or []):
            text = str(page.get("text") or "").strip()
            if not text:
                continue
            evidence = _extract_mixed_punctuation_evidence(text)
            if evidence:
                page_no = page.get("page_no")
                return {
                    "evidence": evidence,
                    "location": {
                        "page": page_no,
                        "display_text": f"第 {page_no} 页" if page_no is not None else "PDF 文本附近",
                    },
                }
        return None

    evidence = _extract_mixed_punctuation_evidence(str(parsed.get("text") or ""))
    if not evidence:
        return None
    return {
        "evidence": evidence,
        "location": {"scope": "document", "display_text": "文档文本附近"},
    }


def _build_text_hit_location(parsed: dict[str, Any], offset: int) -> dict[str, Any]:
    kind = str(parsed.get("kind") or "")
    if kind == "docx":
        matched_paragraph = _find_paragraph_by_offset(parsed, offset)
        return _issue_location_from_paragraph(matched_paragraph)

    if kind == "tex":
        matched_item = _find_tex_paragraph_by_offset(parsed, offset)
        return _issue_location_from_tex(matched_item) if matched_item else {"offset": offset, "display_text": "源码文本附近"}

    if kind == "pdf":
        page = _find_pdf_page_by_offset(parsed, offset)
        page_no = page.get("page_no") if page else None
        return {
            "page": page_no,
            "offset": offset,
            "display_text": f"第 {page_no} 页" if page_no is not None else "PDF 文本附近",
        }

    return {"offset": offset, "display_text": "文档文本附近"}


def _build_text_hit_evidence(parsed: dict[str, Any], start: int, end: int, *, default_text: str) -> str:
    kind = str(parsed.get("kind") or "")
    if kind == "docx":
        matched_paragraph = _find_paragraph_by_offset(parsed, start)
        if matched_paragraph:
            return str(matched_paragraph.get("text") or "").strip() or _build_evidence_excerpt(default_text, start, end)

    if kind == "tex":
        matched_item = _find_tex_paragraph_by_offset(parsed, start)
        if matched_item:
            return str(matched_item.get("text") or "").strip() or _build_evidence_excerpt(default_text, start, end)

    if kind == "pdf":
        matched_page = _find_pdf_page_by_offset(parsed, start)
        if matched_page:
            return _build_evidence_excerpt(str(matched_page.get("text") or ""), 0, len(str(matched_page.get("text") or "")))

    return _build_evidence_excerpt(default_text, start, end)


def _build_paragraph_evidence_excerpt(paragraph: dict[str, Any] | None, *, max_len: int = 60) -> str:
    text = re.sub(r"\s+", " ", str((paragraph or {}).get("text") or "")).strip()
    if not text:
        return ""
    sentences = [segment.strip() for segment in re.split(r"(?<=[。！？；.!?])\s*", text) if segment.strip()]
    snippet = sentences[0] if sentences else text
    if len(snippet) <= max_len:
        return snippet
    return f"{snippet[:max_len].rstrip()}..."


def _find_tex_paragraph_by_offset(parsed: dict[str, Any], offset: int) -> dict[str, Any] | None:
    paragraphs = [item for item in list(parsed.get("paragraphs") or []) if str(item.get("text") or "").strip()]
    cursor = 0
    for item in paragraphs:
        text = str(item.get("text") or "")
        start = cursor
        end = cursor + len(text)
        if start <= offset <= end:
            return item
        cursor = end + 1
    return paragraphs[0] if paragraphs else None


def _find_pdf_page_by_offset(parsed: dict[str, Any], offset: int) -> dict[str, Any] | None:
    pages = [item for item in list(parsed.get("pages") or []) if str(item.get("text") or "").strip()]
    cursor = 0
    for page in pages:
        text = str(page.get("text") or "")
        start = cursor
        end = cursor + len(text)
        if start <= offset <= end:
            return page
        cursor = end + 1
    return pages[0] if pages else None


def _extract_mixed_punctuation_evidence(text: str) -> str | None:
    content = str(text or "")
    if not content:
        return None

    escaped_zh = re.escape(_ZH_PUNCT)
    escaped_en = re.escape(_EN_PUNCT)
    suspicious_patterns = [
        rf"[\u4e00-\u9fff][{escaped_en}]",
        rf"[{escaped_en}][\u4e00-\u9fff]",
        rf"[A-Za-z0-9][{escaped_zh}]",
        rf"[{escaped_zh}][A-Za-z0-9]",
    ]
    for pattern in suspicious_patterns:
        match = re.search(pattern, content)
        if match:
            return _build_evidence_excerpt(content, match.start(), match.end())

    seen_zh = re.search(rf"[{escaped_zh}]", content)
    seen_en = re.search(rf"[{escaped_en}]", content)
    if not (seen_zh and seen_en):
        return None

    start = min(seen_zh.start(), seen_en.start())
    end = max(seen_zh.end(), seen_en.end())
    return _build_evidence_excerpt(content, start, end)


def _count_mixed_punctuation_hits(parsed: dict) -> int:
    """Count total mixed punctuation occurrences across the document."""
    count = 0
    kind = str(parsed.get("kind") or "")
    escaped_zh = re.escape(_ZH_PUNCT)
    escaped_en = re.escape(_EN_PUNCT)
    patterns = [
        rf"[一-鿿][{escaped_en}]",
        rf"[{escaped_en}][一-鿿]",
        rf"[A-Za-z0-9][{escaped_zh}]",
        rf"[{escaped_zh}][A-Za-z0-9]",
    ]
    if kind == "docx":
        for paragraph in list(parsed.get("paragraphs") or []):
            text = str(paragraph.get("text") or "")
            for pat in patterns:
                count += len(re.findall(pat, text))
    elif kind == "pdf":
        for page in list(parsed.get("pages") or []):
            text = str(page.get("text") or "")
            for pat in patterns:
                count += len(re.findall(pat, text))
    else:
        text = str(parsed.get("text") or "")
        for pat in patterns:
            count += len(re.findall(pat, text))
    return count


def _build_evidence_excerpt(text: str, start: int, end: int, *, radius: int = 12) -> str:
    if len(text) <= 80:
        return text.strip()
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    excerpt = text[left:right].strip()
    if left > 0:
        excerpt = f"...{excerpt}"
    if right < len(text):
        excerpt = f"{excerpt}..."
    return excerpt


def _should_skip_spelling_hit(text: str, wrong: Any, right: Any) -> bool:
    wrong_text = str(wrong or "").strip()
    right_text = str(right or "").strip()
    if not wrong_text or wrong_text == right_text:
        return True
    if re.fullmatch(r"[A-Za-z0-9_.-]+", wrong_text):
        return True
    if re.fullmatch(r"\[[0-9,\-–]+\]", wrong_text):
        return True
    if re.search(r"[=∑√≤≥±×÷\\{}]", text):
        return True
    return False


def _normalize_macro_correct_hits(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        for key in ("errors", "details", "matches", "data"):
            value = result.get(key)
            if isinstance(value, list):
                return [_normalize_macro_correct_hit(item) for item in value if _normalize_macro_correct_hit(item)]
        return []
    if isinstance(result, tuple) and len(result) >= 2 and isinstance(result[1], list):
        return [_normalize_macro_correct_hit(item) for item in result[1] if _normalize_macro_correct_hit(item)]
    if isinstance(result, list):
        return [_normalize_macro_correct_hit(item) for item in result if _normalize_macro_correct_hit(item)]
    return []


def _normalize_macro_correct_batch_hits(result: Any) -> list[tuple[int, dict[str, Any]]]:
    if not isinstance(result, list):
        return []
    normalized: list[tuple[int, dict[str, Any]]] = []
    for idx, item in enumerate(result):
        if not isinstance(item, dict):
            continue
        for hit in _normalize_macro_correct_hits(item):
            normalized.append((idx, hit))
    return normalized


def _normalize_macro_correct_hit(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        return {
            "wrong": item.get("wrong") or item.get("source") or item.get("original"),
            "right": item.get("right") or item.get("target") or item.get("corrected"),
            "begin": item.get("begin") or item.get("start_idx") or item.get("offset") or 0,
            "end": item.get("end") or item.get("end_idx") or item.get("offset_end"),
            "message": item.get("message") or item.get("detail"),
            "suggestion": item.get("suggestion"),
            "rule_id": item.get("rule_id") or item.get("type") or "suggestion",
        }
    if isinstance(item, (list, tuple)) and len(item) >= 4:
        return {
            "wrong": item[0],
            "right": item[1],
            "begin": item[2],
            "end": item[3],
            "message": item[4] if len(item) > 4 else "",
            "suggestion": item[5] if len(item) > 5 else "",
            "rule_id": item[6] if len(item) > 6 else "suggestion",
        }
    return None


def _build_vale_input_text(parsed: dict[str, Any]) -> str:
    lines: list[str] = []
    for paragraph in list(parsed.get("paragraphs") or []):
        text = str(paragraph.get("text") or "").strip()
        if not text:
            continue
        lines.append(text)
    return "\n".join(lines)


def _vale_line_to_paragraph(parsed: dict[str, Any], line_no: int) -> tuple[dict[str, Any], str] | None:
    paragraphs = [item for item in list(parsed.get("paragraphs") or []) if str(item.get("text") or "").strip()]
    if not paragraphs:
        return None
    index = max(0, min(len(paragraphs) - 1, line_no - 1))
    paragraph = paragraphs[index]
    return paragraph, str(paragraph.get("text") or "").strip()[:120]


def _check_heading_rules(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues = []
    headings = list(parsed.get("headings") or [])
    paragraphs = list(parsed.get("paragraphs") or [])

    prev_number = None
    for heading in headings:
        text = str(heading.get("text") or "")
        m = re.match(r"^(\d+(?:\.\d+)*)\s", text)
        if m:
            current = m.group(1)
            current_parts = current.split(".")
            if len(current_parts) > 1:
                try:
                    if int(current_parts[-1]) > 1 and not _has_previous_sibling_heading(headings, current):
                        issues.append(RuleIssue(
                            code="heading.numbering_discontinuous",
                            title="标题编号不连续",
                            severity="medium",
                            category="structure",
                            message=f"标题编号 {current} 缺少前序同级标题。",
                            evidence=text,
                            location=_issue_location_from_paragraph(
                                next((p for p in paragraphs if p.get("index") == heading.get("paragraph_index")), None)
                            ),
                            suggestion="检查标题编号是否从 1 开始并连续递增。",
                            parser_confidence="high",
                        ))
                        break
                except ValueError:
                    pass
            if prev_number:
                prev_parts = prev_number.split(".")
                cur_parts = current.split(".")
                if len(prev_parts) == len(cur_parts):
                    try:
                        prev_num = int(prev_parts[-1])
                        cur_num = int(cur_parts[-1])
                        if cur_num > prev_num + 1:
                            issues.append(RuleIssue(
                                code="heading.numbering_discontinuous",
                                title="标题编号不连续",
                                severity="medium",
                                category="structure",
                                message=f"标题编号从 {prev_number} 跳到 {current}，可能遗漏中间章节。",
                                evidence=text,
                                location=_issue_location_from_paragraph(
                                    next((p for p in paragraphs if p.get("index") == heading.get("paragraph_index")), None)
                                ),
                                suggestion="检查标题编号是否连续。",
                                parser_confidence="high",
                            ))
                    except ValueError:
                        pass
            prev_number = current

    return issues


def _has_previous_sibling_heading(headings: list[dict[str, Any]], current: str) -> bool:
    parts = current.split(".")
    try:
        last = int(parts[-1])
    except ValueError:
        return True
    if last <= 1:
        return True
    expected = ".".join([*parts[:-1], str(last - 1)])
    for heading in headings:
        text = str(heading.get("text") or "")
        match = re.match(r"^(\d+(?:\.\d+)*)\s", text)
        if match and match.group(1) == expected:
            return True
    return False


def _check_figure_table_rules(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues = []
    paragraphs = list(parsed.get("paragraphs") or [])
    text = str(parsed.get("text") or "")
    figure_numbers = []

    for p in paragraphs:
        paragraph_text = str(p.get("text") or "").strip()
        m = re.match(r"^(?:图|Fig(?:ure)?)\s*(\d+(?:[-.]\d+)*)", paragraph_text, re.I)
        if m:
            figure_numbers.append((m.group(1), paragraph_text, p))

    for i in range(1, len(figure_numbers)):
        if not _number_is_next(figure_numbers[i - 1][0], figure_numbers[i][0]):
            issues.append(RuleIssue(
                code="figure.numbering_discontinuous",
                title="图号不连续",
                severity="medium",
                category="structure",
                message=f"图号从 {figure_numbers[i-1][0]} 跳到 {figure_numbers[i][0]}。",
                evidence=f"{figure_numbers[i-1][1]} -> {figure_numbers[i][1]}",
                location=_issue_location_from_paragraph(figure_numbers[i][2]),
                suggestion="检查图号是否连续。",
                parser_confidence="medium",
            ))
            break

    figure_caption_numbers = {_normalize_number(number) for number, _text, _p in figure_numbers}
    figure_refs = {_normalize_number(item) for item in re.findall(r"图\s*(\d+(?:[-.]\d+)*)", text)}
    missing_figure_captions = sorted(figure_refs - figure_caption_numbers)
    if missing_figure_captions:
        issues.append(RuleIssue(
            code="figure.referenced_caption_missing",
            title="正文引用的图号缺少对应图题",
            severity="medium",
            category="structure",
            message=f"正文引用了图 {missing_figure_captions[:5]}，但未识别到对应图题。",
            evidence=f"引用图号: {sorted(figure_refs)}, 图题图号: {sorted(figure_caption_numbers)}",
            location={"display_text": "图题与正文引用"},
            suggestion="补齐对应图题，或统一正文引用和图题编号。",
            parser_confidence="medium",
        ))

    table_titles = list(parsed.get("table_titles") or [])
    table_caption_numbers = {
        _normalize_number(match.group(1))
        for title in table_titles
        for match in [re.match(r"^(?:表|Table)\s*(\d+(?:[-.]\d+)*)", str(title).strip(), re.I)]
        if match
    }
    if not table_caption_numbers:
        for p in paragraphs:
            p_text = str(p.get("text") or "").strip()
            match = re.match(r"^(?:表|Table)\s*(\d+(?:[-.]\d+)*)", p_text, re.I)
            if match:
                table_caption_numbers.add(_normalize_number(match.group(1)))
    table_refs = {_normalize_number(item) for item in re.findall(r"表\s*(\d+(?:[-.]\d+)*)", text)}
    missing_table_captions = sorted(table_refs - table_caption_numbers)
    if missing_table_captions:
        issues.append(RuleIssue(
            code="table.referenced_caption_missing",
            title="正文引用的表号缺少对应表题",
            severity="medium",
            category="structure",
            message=f"正文引用了表 {missing_table_captions[:5]}，但未识别到对应表题。",
            evidence=f"引用表号: {sorted(table_refs)}, 表题编号: {sorted(table_caption_numbers)}",
            location={"display_text": "表题与正文引用"},
            suggestion="补齐对应表题，或统一正文引用和表题编号。",
            parser_confidence="medium",
        ))

    return issues


def _check_formula_rules(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    text = str(parsed.get("text") or "")
    defined = {_normalize_number(item) for item in list(parsed.get("formula_numbers") or []) if str(item).strip()}
    if not defined:
        defined = {_normalize_number(item) for item in re.findall(r"[（(]\s*(\d+(?:[-.]\d+)*)\s*[）)]", text)}
    referenced = {_normalize_number(item) for item in re.findall(r"(?:式|公式)\s*[（(]\s*(\d+(?:[-.]\d+)*)\s*[）)]", text)}
    combined = sorted(defined | referenced, key=_number_sort_key)
    missing_between = _missing_numbers_in_sequence(combined)
    if missing_between:
        issues.append(RuleIssue(
            code="formula.numbering_discontinuous",
            title="公式编号不连续",
            severity="medium",
            category="structure",
            message=f"公式编号可能缺少 {missing_between[:5]}。",
            evidence=f"公式编号: {combined}",
            location={"display_text": "公式编号"},
            suggestion="检查公式编号是否按章节连续排列，正文引用是否与公式编号一致。",
            parser_confidence="medium",
        ))
    missing_defined = sorted(referenced - defined)
    if missing_defined:
        issues.append(RuleIssue(
            code="formula.referenced_number_missing",
            title="正文引用的公式编号缺少对应公式",
            severity="medium",
            category="structure",
            message=f"正文引用了公式 {missing_defined[:5]}，但未识别到对应公式编号。",
            evidence=f"引用公式: {sorted(referenced)}, 公式编号: {sorted(defined)}",
            location={"display_text": "公式引用"},
            suggestion="补齐对应公式编号，或统一正文中的公式引用。",
            parser_confidence="medium",
        ))
    return issues


def _normalize_number(value: Any) -> str:
    return str(value or "").strip().replace(".", "-").replace("－", "-").replace("–", "-")


def _number_sort_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in _normalize_number(value).split("-"):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _number_is_next(previous: str, current: str) -> bool:
    prev_parts = list(_number_sort_key(previous))
    cur_parts = list(_number_sort_key(current))
    if len(prev_parts) != len(cur_parts) or not prev_parts or not cur_parts:
        return True
    if prev_parts[:-1] != cur_parts[:-1]:
        return True
    return cur_parts[-1] == prev_parts[-1] + 1


def _missing_numbers_in_sequence(numbers: list[str]) -> list[str]:
    normalized = sorted({_normalize_number(number) for number in numbers if number}, key=_number_sort_key)
    missing: list[str] = []
    for previous, current in zip(normalized, normalized[1:]):
        prev_parts = list(_number_sort_key(previous))
        cur_parts = list(_number_sort_key(current))
        if len(prev_parts) != len(cur_parts) or prev_parts[:-1] != cur_parts[:-1]:
            continue
        if cur_parts[-1] > prev_parts[-1] + 1:
            prefix = "-".join(str(item) for item in cur_parts[:-1])
            for value in range(prev_parts[-1] + 1, cur_parts[-1]):
                missing.append(f"{prefix}-{value}" if prefix else str(value))
    return missing



def _find_reference_boundary(text: str) -> int:
    """Find the character position where the reference list begins."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in {"参考文献", "References", "Bibliography", "REFERENCES"}:
            # Verify it looks like a section header (short line, no brackets)
            if len(stripped) < 20 and not re.match(r"^\[\d+\]", stripped):
                return text.find(line)
    return -1

def _check_reference_rules(parsed: dict[str, Any]) -> list[RuleIssue]:
    issues = []
    text = str(parsed.get("text") or "")

    # --- Extract in-text citation numbers ---
    cited_numbers: set[int] = set()
    # Only extract citations from text before the reference list to avoid
    # counting reference entries themselves as in-text citations.
    ref_boundary = _find_reference_boundary(text)
    pre_ref_text = text[:ref_boundary] if ref_boundary > 0 else text
    for m in re.finditer(r"\[(\d+(?:[,,、\-–]\d+)*)\]", pre_ref_text):
        inner = m.group(1)
        for part in re.split(r"[,,、]", inner):
            part = part.strip()
            if "-" in part or "–" in part:
                try:
                    a_str, b_str = re.split(r"[-–]", part)
                    cited_numbers.update(range(int(a_str), int(b_str) + 1))
                except ValueError:
                    pass
            else:
                try:
                    cited_numbers.add(int(part))
                except ValueError:
                    pass

    # --- Extract reference entry numbers with multi-line support ---
    ref_numbers: set[int] = set()
    ref_entries: dict[int, str] = {}
    raw_refs = list(parsed.get("references") or [])
    if raw_refs:
        for line in raw_refs:
            m = re.match(r"^\[(\d+)\]\s*(.+)", str(line).strip())
            if m:
                num = int(m.group(1))
                ref_numbers.add(num)
                ref_entries[num] = m.group(2).strip()
    # Fallback: parse from full text with multi-line entry support
    if not ref_numbers:
        current_num = None
        current_text = ""
        for line in text.splitlines():
            m = re.match(r"^\[(\d+)\]\s*(.+)", line.strip())
            if m:
                if current_num is not None:
                    ref_entries[current_num] = current_text.strip()
                current_num = int(m.group(1))
                current_text = m.group(2)
                ref_numbers.add(current_num)
            elif current_num is not None and line.strip():
                # Continuation of previous entry (wrapped line)
                current_text += " " + line.strip()
        if current_num is not None:
            ref_entries[current_num] = current_text.strip()

    # --- Cross-reference: citation vs bibliography ---
    missing_in_bib = cited_numbers - ref_numbers
    if missing_in_bib:
        issues.append(RuleIssue(
            code="references.citation_missing_in_bibliography",
            title="正文引用在参考文献列表中缺失",
            severity="high",
            category="structure",
            message=f"正文引用了编号 {sorted(missing_in_bib)[:10]} 共 {len(missing_in_bib)} 条，但文末参考文献列表中未找到对应条目。",
            evidence=f"正文引用: {sorted(cited_numbers)[:20]}, 文献列表: {sorted(ref_numbers)[:20]}",
            location={"display_text": "参考文献章节"},
            suggestion="确保正文中每条引用在参考文献列表中都有对应条目。",
            parser_confidence="medium",
            expected={"cited": sorted(cited_numbers), "listed": sorted(ref_numbers)},
            actual={"missing_in_bib": sorted(missing_in_bib)},
        ))

    unused = ref_numbers - cited_numbers
    if unused and len(ref_numbers) > 3:
        issues.append(RuleIssue(
            code="references.unused_reference",
            title="参考文献列表中部分文献未被正文引用",
            severity="low",
            category="structure",
            message=f"参考文献编号 {sorted(unused)[:10]} 共 {len(unused)} 条未在正文中被引用。",
            evidence=f"未引用编号: {sorted(unused)[:10]}",
            location={"display_text": "参考文献章节"},
            suggestion="确认这些文献是否确实需要列入，或补充正文引用。",
            parser_confidence="medium",
        ))

    # --- Numbering continuity ---
    if ref_numbers:
        sorted_refs = sorted(ref_numbers)
        gaps = [n for n in range(sorted_refs[0], sorted_refs[-1] + 1) if n not in ref_numbers]
        if gaps:
            issues.append(RuleIssue(
                code="references.numbering_discontinuous",
                title="参考文献编号不连续",
                severity="medium",
                category="structure",
                message=f"参考文献编号缺少 {gaps[:10]}{'...' if len(gaps) > 10 else ''}，共 {len(gaps)} 个缺口。",
                evidence=f"编号范围: {sorted_refs[0]}-{sorted_refs[-1]}，现有: {sorted_refs}",
                location={"display_text": "参考文献章节"},
                suggestion="检查参考文献列表编号是否从 1 开始连续排列。",
                parser_confidence="high",
                expected={"continuous_from": sorted_refs[0], "continuous_to": sorted_refs[-1]},
                actual={"missing_numbers": gaps},
            ))

    # --- Per-entry format analysis with statistics ---
    if ref_entries:
        format_issues = []
        for num in sorted(ref_entries)[:50]:
            entry_text = ref_entries[num]
            check = _analyze_reference_entry(entry_text)
            if check["problems"]:
                format_issues.append({"number": num, "problems": check["problems"], "text": entry_text[:120]})
        if format_issues:
            bad_count = len(format_issues)
            total = len(ref_entries)
            all_problems = list(dict.fromkeys(p for fi in format_issues for p in fi["problems"]))
            sample = format_issues[0]
            issues.append(RuleIssue(
                code="references.entry_format_incomplete",
                title="参考文献著录信息不完整",
                severity="medium",
                category="structure",
                message=f"{bad_count}/{total} 条参考文献存在格式问题: {'; '.join(all_problems[:5])}。",
                evidence=f"[{sample['number']}] {sample['text']}",
                location={"display_text": "参考文献章节"},
                suggestion="按 GB/T 7714 标准补全各条目缺失的字段。常见期刊格式: [序号] 作者. 题名[J]. 刊名, 年, 卷(期): 页码.",
                expected={"required_fields": ["author", "title", "year", "source"]},
                actual={"bad_count": bad_count, "total_count": total, "common_problems": all_problems},
                parser_confidence="medium",
            ))
    elif not ref_numbers and cited_numbers:
        issues.append(RuleIssue(
            code="references.bibliography_not_found",
            title="未识别到参考文献列表",
            severity="high",
            category="structure",
            message="正文中有引用编号但文末未找到参考文献列表。",
            evidence=f"正文引用: {sorted(cited_numbers)[:20]}",
            location={"display_text": "文末区域"},
            suggestion="在文末添加参考文献列表，每条以 [序号] 开头。",
            parser_confidence="high",
        ))

    return issues


def _analyze_reference_entry(text: str) -> dict:
    """Analyze a single reference entry for GB/T 7714 compliance."""
    problems = []
    content = str(text or "").strip()
    if not content:
        return {"problems": ["empty"]}

    has_type = bool(re.search(r"\[[A-Z]{1,3}(?:/[A-Z]{1,3})?\]", content))
    has_year = bool(re.search(r"(?:19|20)\d{2}", content))
    has_source = bool(re.search(r"\][^.[\]]+\.[^.[\]]*$", content)) or bool(re.search(r"\d{4}[,，]\s*\d+", content))
    has_vol_pages = bool(re.search(r"\d{4}[,，]\s*\d+", content)) or bool(re.search(r"\d+\(\d+\)", content)) or bool(re.search(r":\s*\d+-\d+", content))
    has_period_end = content.rstrip().endswith(".")

    if not has_year:
        problems.append("缺少年份")
    if not has_type:
        problems.append("缺少文献类型标识[J/M/D]")
    if not has_source:
        problems.append("缺少刊名/出版源")
    if not has_vol_pages:
        problems.append("缺少卷期页码")
    if not has_period_end:
        problems.append("末尾缺句号")

    return {"problems": problems}


def _reference_entry_has_basic_gbt7714_shape(line: str) -> bool:
    return len(_analyze_reference_entry(line)["problems"]) <= 2


def _check_word_artifact_rules(parsed: dict[str, Any]) -> list[RuleIssue]:
    metadata = dict(parsed.get("word_metadata") or {})
    comment_count = int(metadata.get("comment_count") or 0)
    revision_count = int(metadata.get("revision_count") or 0)
    hidden_text_count = int(metadata.get("hidden_text_count") or 0)
    if comment_count <= 0 and revision_count <= 0 and hidden_text_count <= 0:
        return []
    return [
        RuleIssue(
            code="word.comments_or_revisions_present",
            title="Word 文档存在批注、修订或隐藏文字痕迹",
            severity="medium",
            category="word",
            message="提交前应删除批注、接受或拒绝修订，并检查隐藏文字。",
            evidence=f"comments={comment_count}, revisions={revision_count}, hidden_text={hidden_text_count}",
            location={"display_text": "Word 文档元数据"},
            suggestion="在 Word 中关闭修订并清理批注、隐藏文字后重新提交最终版。",
            parser_confidence="high",
            actual={
                "comment_count": comment_count,
                "revision_count": revision_count,
                "hidden_text_count": hidden_text_count,
            },
        )
    ]


def _dedupe_issues(issues: list[RuleIssue]) -> list[RuleIssue]:
    deduped: list[RuleIssue] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in issues:
        key = (
            item.category,
            str(item.location.get("display_text") or item.location),
            item.engine,
            item.evidence,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return _merge_similar_issues(deduped)


def _merge_similar_issues(issues: list[RuleIssue]) -> list[RuleIssue]:
    grouped: dict[tuple[str, str], RuleIssue] = {}
    preserved: list[RuleIssue] = []
    for item in issues:
        if item.engine == "rule":
            preserved.append(item)
            continue
        display_text = str(item.location.get("display_text") or item.location)
        key = (item.category, display_text)
        current = grouped.get(key)
        if current is None:
            grouped[key] = item
            continue
        grouped[key] = _pick_better_issue(current, item)
    return preserved + list(grouped.values())


def _pick_better_issue(left: RuleIssue, right: RuleIssue) -> RuleIssue:
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    left_score = (
        severity_rank.get(left.severity, 0),
        len(left.evidence or ""),
        1 if left.engine in {"pycorrector", "macro_correct", "languagetool", "vale"} else 0,
    )
    right_score = (
        severity_rank.get(right.severity, 0),
        len(right.evidence or ""),
        1 if right.engine in {"pycorrector", "macro_correct", "languagetool", "vale"} else 0,
    )
    return right if right_score > left_score else left
