"""Build Review Evidence Pack from paper format check results.

The evidence pack bridges structured rule-check output to the Ai-Review LLM prompt.
It reduces noise, controls cost, and gives the model concrete evidence to work with.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def build_review_evidence_pack(
    *,
    parsed: dict[str, Any],
    check_result: dict[str, Any],
    file_name: str,
) -> dict[str, Any]:
    document_type = str(check_result.get("document_type") or parsed.get("kind") or "unknown")
    template_id = str(check_result.get("template_id") or "generic_cn_thesis")

    outline = _build_outline(parsed, document_type)
    style_summary = _build_style_summary(parsed, document_type)
    evidence_snippets = _collect_evidence_snippets(parsed, check_result, document_type)

    return {
        "document": {
            "file_name": file_name,
            "document_type": document_type,
            "template_id": template_id,
            "page_count": _page_count(parsed, document_type),
            "word_count": _word_count(parsed),
        },
        "score": check_result.get("score", 0),
        "limitations": list(check_result.get("limitations") or []),
        "outline": outline,
        "issues": list(check_result.get("issues") or []),
        "evidence_snippets": evidence_snippets,
        "style_summary": style_summary,
    }


def _build_outline(parsed: dict[str, Any], document_type: str) -> list[dict[str, Any]]:
    headings = list(parsed.get("headings") or [])
    if not headings and document_type == "tex":
        sections = list(parsed.get("sections") or [])
        return [
            {"level": 1, "title": str(item.get("title") or ""), "line": item.get("line")}
            for item in sections
        ]
    return [
        {
            "level": int(item.get("level") or 0),
            "title": str(item.get("text") or ""),
            "paragraph_index": item.get("paragraph_index"),
        }
        for item in headings
    ]


def _build_style_summary(parsed: dict[str, Any], document_type: str) -> dict[str, Any]:
    if document_type == "docx":
        return _docx_style_summary(parsed)
    if document_type == "tex":
        return _tex_style_summary(parsed)
    if document_type == "pdf":
        return _pdf_style_summary(parsed)
    return {}


def _docx_style_summary(parsed: dict[str, Any]) -> dict[str, Any]:
    paragraphs = list(parsed.get("paragraphs") or [])
    body_paragraphs = [
        item for item in paragraphs
        if str(item.get("text") or "").strip() and not item.get("heading_level")
    ]
    font_names: Counter[str] = Counter()
    font_sizes: Counter[str] = Counter()
    line_spacings: Counter[str] = Counter()
    for p in body_paragraphs:
        fn = p.get("font_name") or p.get("font_name_resolved") or p.get("font_name_raw")
        if fn:
            font_names[str(fn)] += 1
        fs = p.get("font_size_pt") or p.get("font_size_resolved") or p.get("font_size_raw")
        if fs is not None:
            font_sizes[str(float(fs))] += 1
        ls = p.get("line_spacing")
        if ls is not None:
            line_spacings[str(float(ls))] += 1

    page = dict(parsed.get("page_layout") or {})
    return {
        "body_paragraph_count": len(body_paragraphs),
        "style_evidence_scope": "all_body_paragraphs",
        "font_names": sorted(font_names) if font_names else [],
        "font_name_counts": dict(font_names.most_common(20)),
        "font_sizes": sorted(float(item) for item in font_sizes) if font_sizes else [],
        "font_size_counts": dict(font_sizes.most_common(20)),
        "line_spacing_values": sorted(float(item) for item in line_spacings) if line_spacings else [],
        "line_spacing_counts": dict(line_spacings.most_common(20)),
        "margin_cm": {
            "top": page.get("top_margin_cm"),
            "bottom": page.get("bottom_margin_cm"),
            "left": page.get("left_margin_cm"),
            "right": page.get("right_margin_cm"),
        },
    }


def _tex_style_summary(parsed: dict[str, Any]) -> dict[str, Any]:
    commands = dict(parsed.get("commands") or {})
    packages = list(parsed.get("packages") or [])
    return {
        "documentclass": commands.get("documentclass", ""),
        "packages": packages,
        "figure_count": int(parsed.get("figure_count") or 0),
        "table_count": int(parsed.get("table_count") or 0),
    }


def _pdf_style_summary(parsed: dict[str, Any]) -> dict[str, Any]:
    pages = list(parsed.get("pages") or [])
    return {
        "layout": dict(parsed.get("layout_summary") or parsed.get("layout") or {}),
        "font_summary": dict(parsed.get("font_summary") or {}),
        "font_size_summary": dict(parsed.get("font_size_summary") or {}),
        "page_count": int(parsed.get("page_count") or len(pages) or 0),
        "reference_count": len(list(parsed.get("references") or [])),
        "page_text_lengths": [
            len(str(page.get("text") or ""))
            for page in pages[:20]
        ],
    }


def _collect_evidence_snippets(
    parsed: dict[str, Any],
    check_result: dict[str, Any],
    document_type: str,
) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    issues = list(check_result.get("issues") or [])
    issue_codes = {item.get("code", "") for item in issues}

    if document_type == "docx":
        paragraphs = list(parsed.get("paragraphs") or [])
        for p in paragraphs:
            text = str(p.get("text") or "").strip()
            if not text:
                continue
            related: list[str] = []
            if not p.get("heading_level"):
                if p.get("line_spacing") is not None and float(p.get("line_spacing", 1)) < 1.15:
                    related.append("style.line_spacing_small")
                if p.get("first_line_indent_pt") is not None and float(p.get("first_line_indent_pt", 0)) < 1:
                    related.append("style.paragraph_indent_missing")
            if related:
                snippets.append({
                    "id": f"E{len(snippets) + 1}",
                    "source": "paragraph",
                    "location": f"paragraph {p.get('index')}",
                    "text": text[:300],
                    "related_issue_codes": related,
                })
                if len(snippets) >= 10:
                    break

    elif document_type == "tex":
        sections = list(parsed.get("sections") or [])
        for s in sections[:10]:
            snippets.append({
                "id": f"E{len(snippets) + 1}",
                "source": "tex_section",
                "location": f"line {s.get('line')}",
                "text": str(s.get("title") or "")[:300],
                "related_issue_codes": [],
            })

    elif document_type == "pdf":
        pages = list(parsed.get("pages") or [])
        for page in pages[:10]:
            text = str(page.get("text") or "").strip()
            if not text:
                continue
            snippets.append({
                "id": f"E{len(snippets) + 1}",
                "source": "pdf_page",
                "location": f"page {page.get('page_no')}",
                "text": text[:300],
                "related_issue_codes": sorted(issue_codes),
            })

    return snippets[:15]


def _page_count(parsed: dict[str, Any], document_type: str) -> int | None:
    if document_type == "pdf":
        return parsed.get("page_count")
    if document_type == "docx":
        sections = list(parsed.get("sections") or [])
        return len(sections) or None
    return None


def _word_count(parsed: dict[str, Any]) -> int | None:
    text = str(parsed.get("text") or "")
    return len(text.replace("\n", " ").split()) if text.strip() else None
