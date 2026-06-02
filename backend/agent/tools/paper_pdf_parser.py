"""Enhanced PDF parser using PyMuPDF for font, size, coordinate, layout extraction,
and statistical paragraph/heading reconstruction."""
from __future__ import annotations

import re
from collections import Counter
from io import BytesIO
from typing import Any


def parse_pdf_enhanced(content: bytes) -> dict[str, Any]:
    """Parse PDF with PyMuPDF, extracting font, size, layout, and structural information."""
    try:
        import fitz
    except ImportError:
        raise ValueError("PyMuPDF (fitz) not installed. Run: pip install PyMuPDF")

    doc = fitz.open(stream=content, filetype="pdf")
    pages_data = []
    all_text_parts = []
    font_summary: dict[str, int] = {}
    font_size_summary: dict[str, int] = {}
    all_spans: list[dict[str, Any]] = []

    for page_no, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        page_text_parts = []
        page_blocks = []
        page_spans = []

        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_spans = []
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    font_name = span.get("font", "")
                    font_size = round(span.get("size", 0), 1)
                    bbox = list(span.get("bbox", []))
                    is_bold = "Bold" in font_name or "bold" in font_name

                    font_summary[font_name] = font_summary.get(font_name, 0) + 1
                    size_key = str(font_size)
                    font_size_summary[size_key] = font_size_summary.get(size_key, 0) + 1

                    span_info = {
                        "type": "text",
                        "text": text,
                        "bbox": bbox,
                        "font": font_name,
                        "size": font_size,
                        "is_bold": is_bold,
                        "page_no": page_no,
                    }
                    page_blocks.append(span_info)
                    page_spans.append(span_info)
                    all_spans.append(span_info)
                    line_spans.append(span_info)
                    page_text_parts.append(text)

                # Merge line spans into a line-level text
                if line_spans:
                    line_text = "".join(s["text"] for s in line_spans)

        page_text = " ".join(page_text_parts)
        all_text_parts.append(page_text)
        pages_data.append({
            "page_no": page_no,
            "width_pt": page.rect.width,
            "height_pt": page.rect.height,
            "blocks": page_blocks,
            "text": page_text,
        })

    # Statistical analysis for heading detection
    size_stats = _compute_font_size_stats(font_size_summary)
    layout = _estimate_pdf_layout(pages_data)
    text = "\n".join(all_text_parts)

    # Reconstruct paragraphs from spans
    paragraphs = _reconstruct_paragraphs(all_spans, size_stats)
    headings = _extract_pdf_headings(all_spans, size_stats)
    references = _extract_pdf_reference_lines(text, paragraphs)
    citations = _extract_pdf_citations(text)

    parser_limitations: list[str] = []
    if size_stats.get("dominant_size_count", 0) < 20:
        parser_limitations.append("PDF 文本量较少，字号统计可能不准确，标题识别可能受影响。")
    if not headings:
        parser_limitations.append("PDF 中未检测到明显的标题结构，格式检查将基于全文文本进行。")

    return {
        "kind": "pdf",
        "page_count": len(doc),
        "pages": pages_data,
        "paragraphs": paragraphs,
        "headings": headings,
        "references": references,
        "citations": citations,
        "font_summary": dict(sorted(font_summary.items(), key=lambda x: -x[1])[:10]),
        "font_size_summary": dict(sorted(font_size_summary.items(), key=lambda x: -x[1])[:10]),
        "layout_summary": layout,
        "parser_limitations": parser_limitations,
        "text": text,
    }


def _compute_font_size_stats(size_summary: dict[str, int]) -> dict[str, Any]:
    """Compute statistical distribution of font sizes for heading baseline."""
    if not size_summary:
        return {"dominant_size": 12.0, "dominant_size_count": 0, "p75": 14.0, "p90": 16.0}
    total = sum(size_summary.values())
    # Weight by occurrence count
    all_sizes: list[float] = []
    for size_str, count in size_summary.items():
        try:
            all_sizes.extend([float(size_str)] * count)
        except ValueError:
            pass
    if not all_sizes:
        return {"dominant_size": 12.0, "dominant_size_count": 0, "p75": 14.0, "p90": 16.0}
    sorted_sizes = sorted(all_sizes)
    n = len(sorted_sizes)
    # Dominant size: the most frequently used (body text)
    counter = Counter(round(s, 1) for s in all_sizes)
    dominant = counter.most_common(1)[0]
    return {
        "dominant_size": dominant[0],
        "dominant_size_count": dominant[1],
        "median": sorted_sizes[n // 2],
        "p75": sorted_sizes[int(n * 0.75)],
        "p90": sorted_sizes[int(n * 0.9)],
    }


def _reconstruct_paragraphs(
    spans: list[dict[str, Any]],
    size_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """Reconstruct paragraphs from individual text spans using position and font analysis.

    Uses line spacing heuristics: spans on the same Y-line are merged into one line;
    adjacent lines with similar X-start and font size are grouped into paragraphs.
    """
    if not spans:
        return []

    # Group spans by page
    page_groups: dict[int, list[dict[str, Any]]] = {}
    for span in spans:
        page_groups.setdefault(span.get("page_no", 1), []).append(span)

    paragraphs: list[dict[str, Any]] = []
    dominant_size = size_stats.get("dominant_size", 12.0)

    for page_no in sorted(page_groups):
        page_spans = page_groups[page_no]
        # Sort by Y then X
        page_spans.sort(key=lambda s: (round(s["bbox"][1], 0), s["bbox"][0]))

        # Group into lines by Y coordinate
        lines: list[list[dict[str, Any]]] = []
        y_tolerance = 3.0  # pt tolerance for same line
        for span in page_spans:
            y = span["bbox"][1]
            placed = False
            for line in lines:
                line_y = line[0]["bbox"][1]
                if abs(y - line_y) <= y_tolerance:
                    line.append(span)
                    line.sort(key=lambda s: s["bbox"][0])  # re-sort by X
                    placed = True
                    break
            if not placed:
                lines.append([span])

        if not lines:
            continue

        # Merge consecutive lines into paragraphs
        para_lines: list[list[dict[str, Any]]] = []
        current_para: list[list[dict[str, Any]]] = [lines[0]]

        for i in range(1, len(lines)):
            prev_line = lines[i - 1]
            curr_line = lines[i]

            prev_x_start = prev_line[0]["bbox"][0]
            curr_x_start = curr_line[0]["bbox"][0]
            prev_y_bottom = max(s["bbox"][3] for s in prev_line)
            curr_y_top = min(s["bbox"][1] for s in curr_line)
            gap = curr_y_top - prev_y_bottom

            prev_sizes = [s["size"] for s in prev_line]
            curr_sizes = [s["size"] for s in curr_line]
            avg_prev_size = sum(prev_sizes) / len(prev_sizes) if prev_sizes else dominant_size
            avg_curr_size = sum(curr_sizes) / len(curr_sizes) if curr_sizes else dominant_size

            prev_text = "".join(s["text"] for s in prev_line)
            curr_text = "".join(s["text"] for s in curr_line)

            # Conditions to break paragraph:
            # 1. Large vertical gap (>2x line height)
            # 2. Significant X-start offset (indent change or new section)
            # 3. Font size jump (heading vs body)
            # 4. Previous line ends with period (sentence boundary), current is short
            size_ratio = max(avg_curr_size, avg_prev_size) / max(min(avg_curr_size, avg_prev_size), 1)

            break_para = False
            if gap > max(avg_prev_size, avg_curr_size) * 2.5:
                break_para = True
            elif abs(curr_x_start - prev_x_start) > 30 and len(curr_text) < 30:
                break_para = True
            elif size_ratio > 1.3:
                break_para = True

            if break_para:
                para_lines.append(current_para)
                current_para = [curr_line]
            else:
                current_para.append(curr_line)

        para_lines.append(current_para)

        # Build paragraph objects
        heading_index = 0
        for para_lines_group in para_lines:
            para_text = "".join("".join(s["text"] for s in line) for line in para_lines_group)
            if not para_text.strip():
                continue
            first_line = para_lines_group[0]
            bbox0 = first_line[0]["bbox"]
            bbox_last = para_lines_group[-1][-1]["bbox"]
            avg_size = sum(s["size"] for line in para_lines_group for s in line) / max(
                sum(len(line) for line in para_lines_group), 1
            )
            is_bold = any(s.get("is_bold") for line in para_lines_group for s in line)

            para_info = {
                "index": len(paragraphs),
                "text": para_text.strip(),
                "bbox": [bbox0[0], bbox0[1], bbox_last[2], bbox_last[3]],
                "font_size_pt": round(avg_size, 1),
                "is_bold": is_bold,
                "page_no": page_no,
                "paragraph_role": _infer_pdf_paragraph_role(para_text.strip(), avg_size, is_bold, dominant_size),
            }
            paragraphs.append(para_info)

    # Re-index and compute heading levels after all paragraphs are built
    _assign_pdf_heading_levels(paragraphs, size_stats)
    return paragraphs


def _assign_pdf_heading_levels(
    paragraphs: list[dict[str, Any]],
    size_stats: dict[str, Any],
) -> None:
    """Assign heading levels to paragraphs based on font size and content patterns."""
    dominant = size_stats.get("dominant_size", 12.0)
    p90 = size_stats.get("p90", 16.0)

    for para in paragraphs:
        text = para["text"]
        size = para.get("font_size_pt", dominant)
        is_bold = para.get("is_bold", False)
        size_over_dominant = size - dominant

        # Must be larger than body text to be a heading
        if size_over_dominant < 1.0 and not is_bold:
            continue

        # Check if text looks like a heading
        looks_like_heading = _looks_like_pdf_heading(text)

        if not looks_like_heading:
            # Only assign heading if the text is short AND visually prominent
            if len(text) <= 60 and size_over_dominant >= 2.0:
                pass  # likely a heading
            else:
                continue

        # Determine level
        if size >= p90 or size_over_dominant >= 6:
            level = 1
        elif size_over_dominant >= 3:
            level = 2
        elif size_over_dominant >= 1.5:
            level = 3
        else:
            level = 3

        para["heading_level"] = level
        para["paragraph_role"] = "heading"


def _looks_like_pdf_heading(text: str) -> bool:
    """Check if text looks like a heading based on content patterns."""
    patterns = [
        r"^(?:第[一二三四五六七八九十\d]+[章节部分])",
        r"^\d+(?:\.\d+)*\s+[^\d\s]",
        r"^[一二三四五六七八九十]+[、．.\s]",
        r"^[(（][一二三四五六七八九十\d]+[)）]",
        r"^(?:引言|绪论|前言|结论|总结|展望|参考文献|致谢|附录|Abstract|Introduction|Conclusion|References?)",
    ]
    for pattern in patterns:
        if re.match(pattern, text):
            return True
    return False


def _infer_pdf_paragraph_role(
    text: str, font_size: float, is_bold: bool, dominant_size: float
) -> str:
    """Infer the role of a PDF paragraph based on content and visual properties."""
    if not text:
        return "blank"
    if len(text) <= 80 and font_size > dominant_size + 1:
        return "heading"
    if re.match(r"^\[\d+\]\s+", text):
        return "reference_entry"
    if re.match(r"^(?:图|Fig(?:ure)?\.?)\s*\d+", text, re.I):
        return "figure_caption"
    if re.match(r"^(?:表|Table\.?)\s*\d+", text, re.I):
        return "table_caption"
    if text.startswith("摘要") or text.lower().startswith("abstract"):
        return "abstract_body" if len(text) > 10 else "heading"
    if re.match(r"^(?:关键词|Keywords?)\s*[：:]", text, re.I):
        return "keywords"
    if text in {"参考文献", "References", "Bibliography", "REFERENCES"}:
        return "heading"
    return "body"


def _extract_pdf_headings(
    spans: list[dict[str, Any]],
    size_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract headings from PDF spans using statistical font size analysis."""
    if not spans:
        return []

    dominant = size_stats.get("dominant_size", 12.0)
    p90 = size_stats.get("p90", 16.0)

    # Group spans by page and line
    page_groups: dict[int, list[dict[str, Any]]] = {}
    for span in spans:
        page_groups.setdefault(span.get("page_no", 1), []).append(span)

    headings: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    for page_no in sorted(page_groups):
        page_spans = page_groups[page_no]
        page_spans.sort(key=lambda s: (round(s["bbox"][1], 0), s["bbox"][0]))

        # Group into lines
        lines: list[list[dict[str, Any]]] = []
        for span in page_spans:
            y = span["bbox"][1]
            placed = False
            for line in lines:
                if abs(y - line[0]["bbox"][1]) <= 3.0:
                    line.append(span)
                    line.sort(key=lambda s: s["bbox"][0])
                    placed = True
                    break
            if not placed:
                lines.append([span])

        for line in lines:
            line_text = "".join(s["text"] for s in line).strip()
            if not line_text or len(line_text) > 120:
                continue
            if line_text in seen_texts:
                continue

            sizes = [s["size"] for s in line]
            avg_size = sum(sizes) / len(sizes)
            is_bold = any(s.get("is_bold") for s in line)

            size_over_dominant = avg_size - dominant

            # Heading candidates: significantly larger than body, or bold+numbered
            is_candidate = False
            if size_over_dominant >= 3.0:
                is_candidate = True
            elif size_over_dominant >= 1.0 and is_bold and _looks_like_pdf_heading(line_text):
                is_candidate = True
            elif is_bold and _looks_like_pdf_heading(line_text) and avg_size >= dominant:
                is_candidate = True

            if not is_candidate:
                continue

            if avg_size >= p90 or size_over_dominant >= 6:
                level = 1
            elif size_over_dominant >= 3:
                level = 2
            else:
                level = 3

            seen_texts.add(line_text)
            headings.append({
                "text": line_text,
                "level": level,
                "page": page_no,
                "font_size": round(avg_size, 1),
                "detection_source": "statistical",
            })

    return headings


def _extract_pdf_reference_lines(
    text: str, paragraphs: list[dict[str, Any]]
) -> list[str]:
    """Extract reference entries from PDF text or paragraphs."""
    # First try from paragraphs marked as reference_entry
    ref_paras = [p["text"] for p in paragraphs if p.get("paragraph_role") == "reference_entry"]
    if ref_paras:
        return ref_paras

    # Fallback: find reference section in full text
    lines: list[str] = []
    in_refs = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in {"参考文献", "References", "Bibliography", "REFERENCES"}:
            in_refs = True
            continue
        if in_refs:
            if re.match(r"^\[\d+\]", line):
                lines.append(line)
            elif re.match(r"^(?:致谢|附录|攻读|发表|在学|致 謝|Acknowledgement)", line):
                break
    return lines


def _extract_pdf_citations(text: str) -> list[dict[str, Any]]:
    """Extract citations from PDF text (numeric brackets + author-year)."""
    citations: list[dict[str, Any]] = []

    # Numeric bracket citations
    for match in re.finditer(r"\[\s*(\d+(?:\s*[-－–,，、]\s*\d+)*)\s*\]", text):
        raw = match.group(0)
        inner = match.group(1)
        numbers: list[int] = []
        for part in re.split(r"[,，、]", inner):
            part = part.strip()
            if not part:
                continue
            if "-" in part or "－" in part or "–" in part:
                try:
                    a_str, b_str = re.split(r"[-－–]", part)
                    numbers.extend(range(int(a_str), int(b_str) + 1))
                except ValueError:
                    pass
            else:
                try:
                    numbers.append(int(part))
                except ValueError:
                    pass
        citations.append({"raw": raw, "numbers": numbers, "offset": match.start(), "style": "numeric_bracket"})

    # Author-year parenthetical
    for match in re.finditer(
        r"[(（]\s*([A-Z][a-z]+(?:\s+(?:et\s+al\.?|and|&)\s+[A-Z][a-z]+)?|[一-鿿]{1,6})\s*[,，]\s*((?:19|20)\d{2}[a-z]?)\s*[)）]",
        text,
    ):
        author = match.group(1).strip()
        if re.match(r"^(?:see|cf|e\.g\.|i\.e\.|Fig|Table|Equation)\b", author, re.I):
            continue
        citations.append({
            "raw": match.group(0),
            "author": author,
            "year": match.group(2),
            "offset": match.start(),
            "style": "author_year_paren",
        })

    # Author-year narrative
    for match in re.finditer(
        r"([A-Z][a-z]+(?:\s+(?:et\s+al\.?|and|&)\s+[A-Z][a-z]+)?|[一-鿿]{1,4})\s*[(（]\s*((?:19|20)\d{2}[a-z]?)\s*[)）]",
        text,
    ):
        author = match.group(1).strip()
        preceding = text[max(0, match.start() - 3):match.start()]
        if "[" in preceding or "(" in preceding or "（" in preceding:
            continue
        if re.match(r"^(?:see|cf|e\.g\.|i\.e\.|Fig|Table|Equation|第|图|表)\b", author, re.I):
            continue
        citations.append({
            "raw": match.group(0),
            "author": author,
            "year": match.group(2),
            "offset": match.start(),
            "style": "author_year_narrative",
        })

    citations.sort(key=lambda c: c["offset"])
    return citations


def _estimate_pdf_layout(pages: list[dict[str, Any]]) -> dict[str, Any]:
    if not pages:
        return {}
    first = pages[0]
    width = first.get("width_pt", 595)
    height = first.get("height_pt", 842)

    all_bboxes = []
    for page in pages[:5]:
        for block in page.get("blocks", []):
            if block.get("bbox"):
                all_bboxes.append(block["bbox"])

    if not all_bboxes:
        return {"page_size": _page_size_name(width, height)}

    left = min(b[0] for b in all_bboxes)
    top = min(b[1] for b in all_bboxes)
    right = max(b[2] for b in all_bboxes)
    bottom = max(b[3] for b in all_bboxes)

    return {
        "page_size": _page_size_name(width, height),
        "estimated_margins": {
            "top_cm": round(top * 0.035, 1),
            "bottom_cm": round((height - bottom) * 0.035, 1),
            "left_cm": round(left * 0.035, 1),
            "right_cm": round((width - right) * 0.035, 1),
        },
    }


def _page_size_name(width_pt: float, height_pt: float) -> str:
    if abs(width_pt - 595) < 5 and abs(height_pt - 842) < 5:
        return "A4"
    if abs(width_pt - 612) < 5 and abs(height_pt - 792) < 5:
        return "Letter"
    return f"{width_pt:.0f}x{height_pt:.0f}pt"
