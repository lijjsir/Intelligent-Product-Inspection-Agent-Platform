"""Enhanced PDF parser using PyMuPDF for font, size, coordinate, and layout extraction."""
from __future__ import annotations

from io import BytesIO
from typing import Any


def parse_pdf_enhanced(content: bytes) -> dict[str, Any]:
    """Parse PDF with PyMuPDF, extracting font, size, and layout information."""
    try:
        import fitz
    except ImportError:
        raise ValueError("PyMuPDF (fitz) not installed. Run: pip install PyMuPDF")

    doc = fitz.open(stream=content, filetype="pdf")
    pages_data = []
    all_text_parts = []
    font_summary: dict[str, int] = {}
    font_size_summary: dict[str, int] = {}

    for page_no, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        page_text_parts = []
        page_blocks = []

        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    font_name = span.get("font", "")
                    font_size = round(span.get("size", 0), 1)
                    bbox = list(span.get("bbox", []))

                    font_summary[font_name] = font_summary.get(font_name, 0) + 1
                    size_key = str(font_size)
                    font_size_summary[size_key] = font_size_summary.get(size_key, 0) + 1

                    page_blocks.append({
                        "type": "text",
                        "text": text,
                        "bbox": bbox,
                        "font": font_name,
                        "size": font_size,
                        "is_bold": "Bold" in font_name or "bold" in font_name,
                    })
                    page_text_parts.append(text)

        page_text = " ".join(page_text_parts)
        all_text_parts.append(page_text)
        pages_data.append({
            "page_no": page_no,
            "width_pt": page.rect.width,
            "height_pt": page.rect.height,
            "blocks": page_blocks,
            "text": page_text,
        })

    layout = _estimate_pdf_layout(pages_data)
    text = "\n".join(all_text_parts)

    return {
        "kind": "pdf",
        "page_count": len(doc),
        "pages": pages_data,
        "headings": _extract_pdf_headings(pages_data),
        "font_summary": dict(sorted(font_summary.items(), key=lambda x: -x[1])[:10]),
        "font_size_summary": dict(sorted(font_size_summary.items(), key=lambda x: -x[1])[:10]),
        "layout_summary": layout,
        "text": text,
    }


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


def _extract_pdf_headings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    headings = []
    for page in pages:
        for block in page.get("blocks", []):
            text = block.get("text", "").strip()
            if not text:
                continue
            size = block.get("size", 12)
            is_bold = block.get("is_bold", False)
            if size >= 14 or (is_bold and _is_heading_pattern(text)):
                headings.append({
                    "text": text,
                    "level": 1 if size >= 16 else 2 if size >= 14 else 3,
                    "page": page["page_no"],
                    "font_size": size,
                })
    return headings


def _is_heading_pattern(text: str) -> bool:
    import re
    return bool(re.match(
        r"^(?:第[一二三四五六七八九十\d]+章|第[一二三四五六七八九十\d]+节|\d+(?:\.\d+)*\s)",
        text
    ))
