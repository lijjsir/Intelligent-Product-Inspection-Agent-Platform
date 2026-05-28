"""Split writing guide documents into structured clauses for indexing."""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any


def split_guide_into_clauses(
    parsed: dict[str, Any],
    *,
    template_id: str,
    source_file_name: str = "writing-guide.docx",
) -> list[dict[str, Any]]:
    """Parse a writing guide document and split it into indexable clauses."""
    paragraphs = list(parsed.get("paragraphs") or [])
    clauses: list[dict[str, Any]] = []
    current_section = ""
    current_clause_parts: list[str] = []
    current_clause_title = ""
    current_target_type = ""
    current_category = ""

    for p in paragraphs:
        text = str(p.get("text") or "").strip()
        if not text:
            continue

        heading_level = p.get("heading_level") or 0
        if heading_level >= 1:
            if current_clause_parts:
                clauses.append(_build_clause(
                    template_id=template_id,
                    section_title=current_section,
                    clause_title=current_clause_title,
                    clause_text="\n".join(current_clause_parts),
                    target_type=current_target_type,
                    category=current_category,
                    source_file_name=source_file_name,
                ))
                current_clause_parts = []

            if heading_level == 1:
                current_section = text
            current_clause_title = text
            current_target_type, current_category = _infer_target_and_category(text)
        else:
            current_clause_parts.append(text)

    if current_clause_parts:
        clauses.append(_build_clause(
            template_id=template_id,
            section_title=current_section,
            clause_title=current_clause_title,
            clause_text="\n".join(current_clause_parts),
            target_type=current_target_type,
            category=current_category,
            source_file_name=source_file_name,
        ))

    return clauses


def _build_clause(
    *,
    template_id: str,
    section_title: str,
    clause_title: str,
    clause_text: str,
    target_type: str,
    category: str,
    source_file_name: str,
) -> dict[str, Any]:
    source_hash = hashlib.sha256(clause_text.encode()).hexdigest()[:32]
    clause_id = _stable_clause_id(template_id, section_title, clause_title, source_hash)
    normalized = " ".join(clause_text.split())
    vector_text = f"{section_title} {clause_title} {normalized} {target_type} {category}"

    return {
        "clause_id": clause_id,
        "section_title": section_title,
        "clause_title": clause_title,
        "clause_text": clause_text,
        "normalized_text": normalized,
        "vector_text": vector_text[:2000],
        "target_type": target_type,
        "category": category,
        "rule_codes": _infer_rule_codes(target_type, category, normalized),
        "source_file_name": source_file_name,
        "source_hash": source_hash,
    }


def _stable_clause_id(template_id: str, section: str, title: str, source_hash: str) -> str:
    raw = f"{template_id}:{section}:{title}:{source_hash}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def _infer_target_and_category(text: str) -> tuple[str, str]:
    mapping = [
        ("封面", "cover", "structure"),
        ("声明", "statement", "structure"),
        ("摘要", "abstract", "structure"),
        ("关键词", "keywords", "structure"),
        ("目录", "toc", "structure"),
        ("正文", "body_paragraph", "style"),
        ("字体", "body_paragraph", "style"),
        ("字号", "body_paragraph", "style"),
        ("行距", "body_paragraph", "style"),
        ("标题", "heading", "style"),
        ("页边距", "page_layout", "style"),
        ("页眉", "header_footer", "style"),
        ("页脚", "header_footer", "style"),
        ("页码", "page_number", "style"),
        ("图", "figure", "structure"),
        ("表", "table", "structure"),
        ("公式", "formula", "structure"),
        ("参考文献", "references", "structure"),
        ("引用", "citation", "structure"),
        ("致谢", "acknowledgement", "structure"),
        ("附录", "appendix", "structure"),
    ]
    for keyword, target, cat in mapping:
        if keyword in text:
            return target, cat
    return "body_paragraph", "style"


def _infer_rule_codes(target_type: str, category: str, text: str) -> list[str]:
    codes = []
    if "字体" in text:
        codes.append(f"template.{target_type}.font_mismatch")
    if "字号" in text or "小四" in text or "号" in text:
        codes.append(f"template.{target_type}.font_size_mismatch")
    if "行距" in text or "倍行距" in text:
        codes.append(f"template.{target_type}.line_spacing_mismatch")
    return codes
