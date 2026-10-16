"""Read-only real-PDF extraction evidence; never approves or imports resources.

The command intentionally writes a report even when a PDF needs OCR.  A broken
text layer must be visible to a reviewer, rather than turning into guessed
numbers or an unhelpful process traceback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from agent.tools.file_parsers import parse_file_content
from app.services.standard_candidate_extractor import extract_candidates
from app.services.standard_pdf_importer import extract_pdf_pages, is_unreadable_pdf_text


def _raw_pages(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read the parser's original projection without OCR or normalization."""
    parsed = parse_file_content(path.name, path.read_bytes())
    raw_pages = list(parsed.get("pages") or [])
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(raw_pages, start=1):
        pages.append(
            {
                "page_number": int(page.get("page_no") or page.get("page_number") or index),
                "text": str(page.get("text") or ""),
            }
        )
    if not pages and parsed.get("text"):
        pages.append({"page_number": 1, "text": str(parsed.get("text") or "")})
    page_count = int(parsed.get("page_count") or len(raw_pages) or len(pages))
    return pages, page_count


def _affected_pages(raw_pages: list[dict[str, Any]], error: str) -> list[int]:
    pages = [
        int(page["page_number"])
        for page in raw_pages
        if is_unreadable_pdf_text(str(page.get("text") or ""))
    ]
    if pages:
        return pages
    # Preserve a page number from an OCR error even if the parser returned no
    # usable text for that page.
    return sorted({int(value) for value in re.findall(r"page\s+(\d+)", error, flags=re.I)})


def build_report(path: Path) -> dict[str, Any]:
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        raw_pages, raw_page_count = _raw_pages(path)
    except Exception as exc:  # pragma: no cover - parser/runtime failure
        raw_pages, raw_page_count = [], 0
        raw_error = str(exc)
    else:
        raw_error = ""

    try:
        pages, count = extract_pdf_pages(path)
        candidates = extract_candidates(pages)
    except Exception as exc:  # OCR and parser failures remain reviewable evidence.
        error = str(exc)
        affected = _affected_pages(raw_pages, error)
        return {
            "status": "needs_ocr" if affected or "ocr" in error.lower() else "failed",
            "source_file": path.name,
            "source_sha256": source_hash,
            "pdf_page_count": raw_page_count,
            "parsed_pages": len(raw_pages),
            "affected_pages": affected,
            "raw_pages": raw_pages,
            "candidate_count": 0,
            "candidates": [],
            "auto_confirmed": 0,
            "published": False,
            "extraction_error": error,
            "raw_parse_error": raw_error or None,
            "notice": (
                "未生成正式检测要求。请对受影响页执行中文 OCR，并由专业人员对照原 PDF 核验；"
                "本报告保留原始文本，不对数字、单位或符号做推断。"
            ),
        }

    return {
        "status": "extracted_for_review",
        "source_file": path.name,
        "source_sha256": source_hash,
        "pdf_page_count": count,
        "parsed_pages": len(pages),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "auto_confirmed": 0,
        "published": False,
        "notice": "Local extraction evidence only; original PDF and professional review still required.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero status when extraction needs OCR or otherwise fails.",
    )
    args = parser.parse_args(argv)
    path = Path(args.pdf)
    report = build_report(path)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"candidates", "raw_pages"}}, ensure_ascii=False))
    return 0 if report["status"] == "extracted_for_review" or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
