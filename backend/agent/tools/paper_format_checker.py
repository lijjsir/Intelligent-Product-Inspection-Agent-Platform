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
                    location={"paragraph_index": item.get("paragraph_index"), "heading_level": level},
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
                    location={"paragraph_index": heading.get("paragraph_index")},
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
                    location={"paragraph_index": paragraph.get("index")},
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
    text = str(parsed.get("text") or "")
    for section in list(rules.get("required_sections") or []):
        section_name = str(section)
        if section_name and not _contains_any(text, [section_name]):
            issues.append(
                RuleIssue(
                    code="template.required_section_missing",
                    title=f"模板要求章节缺失：{section_name}",
                    severity="high" if section_name in {"摘要", "参考文献"} else "medium",
                    category="template",
                    message=f"按 {template.get('name')} 规则未识别到“{section_name}”。",
                    evidence=f"未找到模板章节：{section_name}",
                    location={"section": section_name, "template_id": template_id},
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
                        location={"page_layout": parsed_key, "template_id": template_id},
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
                    location={"paragraph_index": paragraph.get("index"), "template_id": template_id},
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
                        location={"paragraph_index": paragraph.get("index"), "template_id": template_id},
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
                    location={"line": item.get("line")},
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
                location={"environment": "figure"},
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
        issues.append(
            RuleIssue(
                code="text.fullwidth_ascii",
                title="全半角字符混用",
                severity="low",
                category="text",
                message="检测到全角英文或数字字符。",
                evidence=seen_fullwidth.group(0),
                location={"offset": seen_fullwidth.start()},
                suggestion="统一改为半角英文和数字。",
            )
        )
    double_space = re.search(r"[^\n]\s{2,}[^\n]", text)
    if double_space:
        issues.append(
            RuleIssue(
                code="text.multiple_spaces",
                title="存在连续空格",
                severity="low",
                category="text",
                message="检测到连续空格。",
                evidence=double_space.group(0),
                location={"offset": double_space.start()},
                suggestion="清理多余空格，保持排版一致。",
            )
        )
    if _mixed_punctuation(text):
        issues.append(
            RuleIssue(
                code="text.mixed_punctuation",
                title="中英文标点混用",
                severity="medium",
                category="text",
                message="检测到中文语境中可能存在中英文标点混用。",
                evidence="文本中同时出现中文和英文标点组合",
                location={"scope": "document"},
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
                    location={"paragraph_index": paragraph.get("index")},
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
        issues.append(
            RuleIssue(
                code=f"languagetool.{str((match.get('rule') or {}).get('id') or 'match').lower()}",
                title="语言校对提示",
                severity="low",
                category="text" if category_name else "text",
                message=message or "检测到可能的语言或标点问题。",
                evidence=evidence[:80],
                location={"file": file_name, "offset": offset, "length": length},
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


def _mixed_punctuation(text: str) -> bool:
    zh_positions = [text.find(ch) for ch in _ZH_PUNCT if ch in text]
    en_positions = [text.find(ch) for ch in _EN_PUNCT if ch in text]
    return bool(zh_positions and en_positions)


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
