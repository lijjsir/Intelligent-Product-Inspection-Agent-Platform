"""Enhanced DOCX parser with style inheritance resolution, table parsing, and citation extraction."""
from __future__ import annotations

import re
import zipfile
from io import BytesIO
from typing import Any


def parse_docx_enhanced(content: bytes) -> dict[str, Any]:
    """Parse DOCX with style inheritance resolution and enhanced extraction."""
    from docx import Document

    doc = Document(BytesIO(content))
    style_cache = _build_style_cache(doc)

    paragraphs = []
    headings = []
    figure_titles = []

    current_section_title = ""
    current_section_level = 0
    current_section_index = 0
    current_paragraph_no = 0

    for index, paragraph in enumerate(doc.paragraphs):
        text = (paragraph.text or "").strip()
        style_name = str(getattr(paragraph.style, "name", "") or "")
        heading_level = _heading_level(style_name)

        font_name_raw, font_name_resolved, style_source = _resolve_font(paragraph, style_cache, style_name)
        font_size_raw, font_size_resolved, size_source = _resolve_font_size(paragraph, style_cache, style_name)

        para_format = paragraph.paragraph_format
        line_spacing = _to_float(getattr(para_format, "line_spacing", None))
        space_before = _to_pt(getattr(para_format, "space_before", None))
        space_after = _to_pt(getattr(para_format, "space_after", None))
        first_line_indent = _to_pt(getattr(para_format, "first_line_indent", None))

        if heading_level:
            current_section_title = text
            current_section_level = heading_level
            current_section_index += 1
            current_paragraph_no = 0
        elif text:
            current_paragraph_no += 1

        item = {
            "index": index,
            "text": text,
            "style_name": style_name,
            "heading_level": heading_level,
            "font_name_raw": font_name_raw,
            "font_name_resolved": font_name_resolved,
            "font_name": font_name_resolved or font_name_raw,
            "font_style_source": style_source,
            "font_size_raw": font_size_raw,
            "font_size_resolved": font_size_resolved,
            "font_size_pt": font_size_resolved or font_size_raw,
            "font_size_source": size_source,
            "line_spacing": line_spacing,
            "space_before_pt": space_before,
            "space_after_pt": space_after,
            "first_line_indent_pt": first_line_indent,
            "section_title": current_section_title,
            "section_level": current_section_level,
            "section_index": current_section_index,
            "paragraph_no": current_paragraph_no if text and not heading_level else 0,
        }
        paragraphs.append(item)

        if heading_level:
            headings.append({
                "text": text,
                "level": heading_level,
                "paragraph_index": index,
                "font_name": font_name_resolved or font_name_raw or "",
                "font_size_pt": font_size_resolved or font_size_raw,
            })

        if text and re.match(r"^(图|Figure)\s*\d+(?:[-.]\d+)*", text, re.I):
            figure_titles.append(text)

    tables = _parse_tables(doc)
    sections_data = _parse_sections_enhanced(doc)
    text_content = "\n".join(p["text"] for p in paragraphs if p["text"])
    citations = _extract_citations(text_content)
    table_titles = _extract_titles(text_content, r"^(?:表|Table)\s*\d+(?:[-.]\d+)*[^\n]*")
    formula_numbers = _extract_formula_numbers(paragraphs, text_content)
    toc_entries = _extract_toc_entries(paragraphs)
    word_metadata = _parse_docx_package_metadata(content)

    return {
        "kind": "docx",
        "paragraphs": paragraphs,
        "headings": headings,
        "figure_titles": figure_titles,
        "table_titles": table_titles,
        "formula_numbers": formula_numbers,
        "toc_entries": toc_entries,
        "tables": tables,
        "sections": sections_data,
        "section_count": len(doc.sections),
        "page_layout": sections_data[0] if sections_data else {},
        "citations": citations,
        "references": _extract_reference_lines(text_content),
        "word_metadata": word_metadata,
        "text": text_content,
    }


def _build_style_cache(doc) -> dict[str, dict[str, Any]]:
    cache = {}
    for style in doc.styles:
        info = {"name": str(style.name) if style.name else "", "type": str(style.type) if style.type else ""}
        try:
            info["font_name"] = style.font.name
            info["font_size"] = style.font.size
        except Exception:
            info["font_name"] = None
            info["font_size"] = None
        try:
            info["line_spacing"] = _to_float(getattr(style.paragraph_format, "line_spacing", None))
        except Exception:
            info["line_spacing"] = None
        cache[str(style.name)] = info
    return cache


def _resolve_font(paragraph, style_cache: dict[str, Any], style_name: str) -> tuple:
    for run in paragraph.runs:
        if run.font.name:
            return run.font.name, run.font.name, "run"

    if style_name and style_name in style_cache:
        fn = style_cache[style_name].get("font_name")
        if fn:
            return None, fn, "paragraph_style"

    if "Normal" in style_cache:
        fn = style_cache["Normal"].get("font_name")
        if fn:
            return None, fn, "normal_style"

    return None, None, "unresolved"


def _resolve_font_size(paragraph, style_cache: dict[str, Any], style_name: str) -> tuple:
    for run in paragraph.runs:
        if run.font.size:
            try:
                return run.font.size.pt, round(run.font.size.pt, 2), "run"
            except Exception:
                pass

    if style_name and style_name in style_cache:
        fs = style_cache[style_name].get("font_size")
        if fs:
            try:
                return None, round(fs.pt, 2), "paragraph_style"
            except Exception:
                pass

    return None, None, "unresolved"


def _parse_tables(doc) -> list[dict[str, Any]]:
    tables = []
    for t_idx, table in enumerate(doc.tables):
        rows = [[cell.text for cell in row.cells] for row in table.rows]
        tables.append({"index": t_idx, "rows": rows, "row_count": len(rows)})
    return tables


def _parse_sections_enhanced(doc) -> list[dict[str, Any]]:
    sections = []
    for section in doc.sections:
        page_width = _to_cm(getattr(section, "page_width", None))
        page_height = _to_cm(getattr(section, "page_height", None))
        sections.append({
            "start_type": str(getattr(getattr(section, "start_type", None), "name", "") or getattr(section, "start_type", "") or ""),
            "page_width_cm": page_width,
            "page_height_cm": page_height,
            "orientation": (
                "landscape"
                if isinstance(page_width, (int, float)) and isinstance(page_height, (int, float)) and page_width > page_height
                else "portrait"
            ),
            "top_margin_cm": _to_cm(getattr(section, "top_margin", None)),
            "bottom_margin_cm": _to_cm(getattr(section, "bottom_margin", None)),
            "left_margin_cm": _to_cm(getattr(section, "left_margin", None)),
            "right_margin_cm": _to_cm(getattr(section, "right_margin", None)),
            "gutter_cm": _to_cm(getattr(section, "gutter", None)),
            "header_distance_cm": _to_cm(getattr(section, "header_distance", None)),
            "footer_distance_cm": _to_cm(getattr(section, "footer_distance", None)),
            "header_text": "\n".join(
                (p.text or "").strip() for p in section.header.paragraphs if (p.text or "").strip()
            ),
            "footer_text": "\n".join(
                (p.text or "").strip() for p in section.footer.paragraphs if (p.text or "").strip()
            ),
        })
    return sections


def _extract_titles(text: str, pattern: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in re.finditer(pattern, text, flags=re.I | re.M)
        if match.group(0).strip()
    ]


def _extract_formula_numbers(paragraphs: list[dict[str, Any]], text: str) -> list[str]:
    numbers: list[str] = []
    for paragraph in paragraphs:
        paragraph_text = str(paragraph.get("text") or "")
        style_name = str(paragraph.get("style_name") or "")
        if "公式" not in style_name and not re.search(r"[=∑√≤≥±×÷]", paragraph_text):
            continue
        for match in re.finditer(r"[（(]\s*(\d+(?:[-.]\d+)*)\s*[）)]", paragraph_text):
            number = match.group(1)
            if _plausible_formula_number(number) and number not in numbers:
                numbers.append(number)
    return numbers


def _plausible_formula_number(number: str) -> bool:
    parts = re.split(r"[-.]", str(number or ""))
    if not 1 <= len(parts) <= 3:
        return False
    try:
        values = [int(part) for part in parts]
    except ValueError:
        return False
    return values[0] <= 20 and all(0 <= item <= 99 for item in values)


def _extract_toc_entries(paragraphs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for paragraph in paragraphs:
        style_name = str(paragraph.get("style_name") or "").lower()
        text = str(paragraph.get("text") or "").strip()
        if not text:
            continue
        if not (style_name.startswith("toc") or "table of figures" in style_name):
            continue
        title = text
        page = ""
        if "\t" in text:
            title, page = text.rsplit("\t", 1)
        entries.append({
            "title": title.strip(),
            "page": page.strip(),
            "style_name": paragraph.get("style_name"),
            "level": _toc_level(style_name),
            "paragraph_index": paragraph.get("index"),
        })
    return entries


def _toc_level(style_name: str) -> int:
    match = re.search(r"toc\s*(\d+)", style_name)
    if match:
        return int(match.group(1))
    return 1


def _extract_reference_lines(text: str) -> list[str]:
    lines = []
    in_refs = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Only trigger on exact section header, not on entries that contain the word
        if in_refs:
            if re.match(r"^\[\d+\]", line):
                lines.append(line)
            # Stop at next major section heading
            elif re.match(r"^(?:致谢|附录|攻读|发表|在学|致 謝)", line):
                break
        else:
            if line in {"参考文献", "References", "Bibliography", "REFERENCES"}:
                in_refs = True
    return lines


def _parse_docx_package_metadata(content: bytes) -> dict[str, Any]:
    metadata = {
        "comment_count": 0,
        "revision_count": 0,
        "hidden_text_count": 0,
        "field_count": 0,
    }
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "word/comments.xml" in names:
                comments_xml = archive.read("word/comments.xml").decode("utf-8", errors="ignore")
                metadata["comment_count"] = comments_xml.count("<w:comment ")
            document_xml = archive.read("word/document.xml").decode("utf-8", errors="ignore") if "word/document.xml" in names else ""
            metadata["revision_count"] = len(re.findall(r"<w:(?:ins|del|moveFrom|moveTo)\b", document_xml))
            metadata["hidden_text_count"] = document_xml.count("<w:vanish")
            metadata["field_count"] = document_xml.count("<w:fldChar") + document_xml.count("<w:instrText")
    except Exception:
        return metadata
    return metadata


def _extract_citations(text: str) -> list[dict[str, Any]]:
    citations = []
    for m in re.finditer(r"\[(\d+(?:[,,\-–]\d+)*)\]", text):
        raw = m.group(0)
        inner = m.group(1)
        numbers: list[int] = []
        for part in re.split(r"[,,，]", inner):
            part = part.strip()
            if "-" in part or "–" in part:
                try:
                    a_str, b_str = re.split(r"[-–]", part)
                    numbers.extend(range(int(a_str), int(b_str) + 1))
                except ValueError:
                    pass
            else:
                try:
                    numbers.append(int(part))
                except ValueError:
                    pass
        citations.append({"raw": raw, "numbers": numbers, "offset": m.start()})
    return citations


def _heading_level(style_name: str) -> int:
    match = re.search(r"heading\s*(\d+)", style_name, re.I)
    if match:
        return int(match.group(1))
    if "标题" in style_name:
        zh_match = re.search(r"标题\s*(\d+)", style_name)
        if zh_match:
            return int(zh_match.group(1))
        return 1
    return 0


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_pt(value) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value.pt), 2)
    except Exception:
        return None


def _to_cm(value) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value.cm), 2)
    except Exception:
        return None
