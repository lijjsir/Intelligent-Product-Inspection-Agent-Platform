from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from agent.tools.paper_format_templates import get_paper_template


DEFAULT_TEMPLATE_ID = "generic_cn_thesis"

_ZH_PUNCT = "，。；：？！、“”‘’（）《》【】"
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "evidence": self.evidence,
            "location": dict(self.location),
            "suggestion": self.suggestion,
        }


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

    if document_type == "docx":
        issues.extend(_check_docx_structure(parsed))
        issues.extend(_check_docx_style(parsed))
        issues.extend(_check_text_norms(parsed))
        issues.extend(_check_template_rules(parsed, template=template, document_type=document_type))
    elif document_type == "tex":
        issues.extend(_check_tex_structure(parsed))
        issues.extend(_check_text_norms(parsed))
        issues.extend(_check_template_rules(parsed, template=template, document_type=document_type))
        limitations.append("LaTeX 仅基于源码检查，不代表最终 PDF 版面完全合规。")
    elif document_type == "pdf":
        issues.extend(_check_pdf_structure(parsed))
        issues.extend(_check_text_norms(parsed))
        issues.extend(_check_template_rules(parsed, template=template, document_type=document_type))
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

    issues.extend(_dedupe_issues(_check_language_tool(parsed, file_name=file_name)))
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
                message="文档中未识别到“摘要”部分。",
                evidence="未找到标题或段落“摘要”",
                location={"section": "abstract"},
                suggestion="补充中文摘要并按模板放在前置部分。",
            )
        )
    if not _contains_any(text, ["关键词", "关键字"]):
        issues.append(
            RuleIssue(
                code="structure.keywords_missing",
                title="缺少关键词",
                severity="medium",
                category="structure",
                message="文档中未识别到“关键词/关键字”部分。",
                evidence="未找到关键词字段",
                location={"section": "keywords"},
                suggestion="按模板添加关键词字段。",
            )
        )
    if not _contains_any(text, ["参考文献"]):
        issues.append(
            RuleIssue(
                code="structure.references_missing",
                title="缺少参考文献",
                severity="high",
                category="structure",
                message="文档中未识别到“参考文献”部分。",
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
                suggestion="检查图题是否按模板书写，例如“图 1 标题”。",
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
                message="PDF 文本中未识别到“摘要”部分。",
                evidence="未找到标题或段落“摘要”",
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
                message="PDF 文本中未识别到“关键词/关键字”部分。",
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
                message="PDF 文本中未识别到“参考文献”部分。",
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
    body_candidates = [item for item in paragraphs if not item.get("heading_level") and item.get("text")]
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
                    message=f"按 {template.get('name')} 规则未识别到“{section_name}”。",
                    evidence=f"未找到模板章节：{section_name}",
                    location={
                        "section": section_name,
                        "template_id": template_id,
                        "display_text": f"模板要求存在《{section_name}》章节",
                    },
                    suggestion=f"按学校模板补充或核对“{section_name}”章节。",
                )
            )

    if document_type != "docx":
        return issues

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
                    )
                )
                break

    body_font = dict(rules.get("body_font") or {})
    body_candidates = [
        item for item in list(parsed.get("paragraphs") or [])
        if item.get("text") and not item.get("heading_level")
    ]
    expected_names = {
        str(body_font.get("zh") or "").lower(),
        str(body_font.get("en") or "").lower(),
    } - {""}
    expected_size = body_font.get("size_pt")
    for paragraph in body_candidates[:20]:
        actual_name = str(paragraph.get("font_name") or "").lower()
        actual_size = paragraph.get("font_size_pt")
        name_mismatch = bool(expected_names and actual_name and actual_name not in expected_names)
        size_mismatch = (
            isinstance(expected_size, (int, float))
            and isinstance(actual_size, (int, float))
            and abs(float(actual_size) - float(expected_size)) > 0.2
        )
        if name_mismatch or size_mismatch:
            issues.append(
                RuleIssue(
                    code="template.body_font_mismatch",
                    title="正文字体或字号与学校模板不一致",
                    severity="medium",
                    category="template",
                    message="识别到正文段落字体或字号与模板建议不一致。",
                    evidence=(
                        f"段落 {paragraph.get('index')}: "
                        f"font={paragraph.get('font_name')}, size={paragraph.get('font_size_pt')}"
                    ),
                    location={**_issue_location_from_paragraph(paragraph), "template_id": template_id},
                    suggestion="按学校模板统一正文字体和字号。",
                )
            )
            break

    expected_spacing = rules.get("line_spacing")
    if isinstance(expected_spacing, (int, float)):
        for paragraph in body_candidates[:20]:
            actual_spacing = paragraph.get("line_spacing")
            if isinstance(actual_spacing, (int, float)) and abs(float(actual_spacing) - float(expected_spacing)) > 0.1:
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
        issues.append(
            RuleIssue(
                code="text.mixed_punctuation",
                title="中英文标点混用",
                severity="medium",
                category="text",
                message="检测到中文语境中可能存在中英文标点混用。",
                evidence=str(mixed_punctuation_hit.get("evidence") or ""),
                location=dict(mixed_punctuation_hit.get("location") or {"scope": "document"}),
                suggestion="统一中文正文中的标点风格。",
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
    return issues


def _check_language_tool(parsed: dict[str, Any], *, file_name: str) -> list[RuleIssue]:
    base_url = str(settings.paper_check_languagetool_url or "").strip().rstrip("/")
    if not base_url:
        return []
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
                evidence=evidence[:80],
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
            )
        )
    return issues


def _language_tool_suggestion(match: dict[str, Any]) -> str:
    replacements = [str(item.get("value") or "").strip() for item in list(match.get("replacements") or []) if item.get("value")]
    if replacements:
        return f"可优先参考替换建议：{', '.join(replacements[:3])}"
    return "请结合上下文人工复核该处表述。"


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


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


def _dedupe_issues(issues: list[RuleIssue]) -> list[RuleIssue]:
    deduped: list[RuleIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for item in issues:
        key = (item.code, item.evidence, str(item.location))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
