from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from agent.rag.knowledge_indexer import KnowledgeIndexer
from agent.rag.retriever import Retriever
from agent.tools.file_parsers import _extract_pdf_headings, parse_file_content
from app.core.exceptions import ValidationError
from app.services.standard_meta_registry import STANDARD_META_REGISTRY


STANDARD_NO_PATTERN = re.compile(r"(?P<number>\d+(?:\.\d+)?)[-_ ](?P<year>\d{4})", re.I)
PDF_GLYPH_CODE_PATTERN = re.compile(r"/G[0-9A-Fa-f]{2,4}")
PDF_REPLACEMENT_CHAR_PATTERN = re.compile(r"[\ufffd□]")
PDF_SYMBOLIC_FONT_CHAR_PATTERN = re.compile(r"[\u7280-\u72ff]")
PDF_CONTROL_CHAR_PATTERN = re.compile(r"[\x80-\x9f]")


def normalize_standard_no(file_name: str) -> str:
    name = Path(str(file_name or "")).name
    normalized = name.replace("+", " ").replace("_", "-")
    lower = normalized.lower()
    match = STANDARD_NO_PATTERN.search(normalized)
    if not match:
        return Path(name).stem
    number = match.group("number")
    year = match.group("year")
    if "gbt" in lower or "gb/t" in lower or "-gbt-" in lower or lower.startswith("gb-t"):
        return f"GB/T {number}-{year}"
    if lower.startswith("gb-18401") or lower.startswith("gb 18401"):
        return f"GB {number}-{year}"
    if lower.startswith("gb"):
        registry_match = STANDARD_META_REGISTRY.get(name)
        if registry_match:
            return str(registry_match["standard_no"])
        return f"GB/T {number}-{year}"
    return f"GB/T {number}-{year}"


def resolve_standard_meta(file_path: str | Path, *, fallback_domain: str | None = None, fallback_product_category: str | None = None) -> dict[str, Any]:
    path = Path(file_path)
    registry = STANDARD_META_REGISTRY.get(path.name)
    if registry:
        return dict(registry)
    standard_no = normalize_standard_no(path.name)
    level = "GB/T" if standard_no.startswith("GB/T") else "GB" if standard_no.startswith("GB ") else "GB/T"
    return {
        "standard_no": standard_no,
        "standard_name": path.stem,
        "domain": fallback_domain or path.parent.name or "通用质检",
        "product_category": fallback_product_category or path.parent.name or "通用标准",
        "standard_level": level,
        "standard_status": "现行",
        "inspection_items": [],
        "image_defect_keywords": [],
    }


def sha256_file(file_path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_pages(file_path: str | Path) -> tuple[list[dict[str, Any]], int]:
    path = Path(file_path)
    content = path.read_bytes()
    parsed = parse_file_content(path.name, content)
    raw_pages = list(parsed.get("pages") or [])
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(raw_pages, start=1):
        text = str(page.get("text") or "").strip()
        if text:
            pages.append({"page_number": int(page.get("page_no") or page.get("page_number") or index), "text": text})
    if not pages:
        text = str(parsed.get("text") or "").strip()
        if text:
            pages.append({"page_number": 1, "text": text})
    pages = repair_unreadable_pdf_pages_with_ocr(pages, file_path=path)
    return pages, int(parsed.get("page_count") or len(raw_pages) or len(pages))


def is_unreadable_pdf_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return False
    symbolic_chars = PDF_SYMBOLIC_FONT_CHAR_PATTERN.findall(compact)
    normal_cjk_count = max(0, len(re.findall(r"[\u4e00-\u9fff]", compact)) - len(symbolic_chars))
    normal_cjk_ratio = normal_cjk_count / max(len(compact), 1)

    glyph_codes = PDF_GLYPH_CODE_PATTERN.findall(compact)
    if len(glyph_codes) >= 8:
        glyph_chars = sum(len(item) for item in glyph_codes)
        if glyph_chars / max(len(compact), 1) >= 0.18:
            return True

    replacement_chars = PDF_REPLACEMENT_CHAR_PATTERN.findall(compact)
    if len(replacement_chars) >= 8 and len(replacement_chars) / max(len(compact), 1) >= 0.08:
        return True

    control_chars = PDF_CONTROL_CHAR_PATTERN.findall(compact)
    if len(control_chars) >= 4 and normal_cjk_ratio < 0.2:
        return True

    if len(symbolic_chars) >= 8 and len(symbolic_chars) / max(len(compact), 1) >= 0.03 and normal_cjk_ratio < 0.2:
        return True

    return False


def ocr_pdf_page_text(file_path: str | Path, *, page_number: int) -> str:
    if shutil.which("tesseract") is None:
        raise ValidationError("OCR fallback requires tesseract with chi_sim language data")
    try:
        import fitz
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise ValidationError(f"OCR fallback requires PyMuPDF: {exc}") from exc

    path = Path(file_path)
    with fitz.open(str(path)) as document:
        page_index = max(0, int(page_number) - 1)
        if page_index >= len(document):
            raise ValidationError(f"page {page_number} is out of range for OCR: {path.name}")
        page = document[page_index]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
            pixmap.save(image_file.name)
            result = subprocess.run(
                ["tesseract", image_file.name, "stdout", "-l", "chi_sim+eng", "--psm", "6"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=90,
                check=False,
            )
    if result.returncode != 0:
        raise ValidationError(f"OCR fallback failed for {path.name} page {page_number}: {result.stderr.strip()}")
    return str(result.stdout or "").strip()


def repair_unreadable_pdf_pages_with_ocr(pages: list[dict[str, Any]], *, file_path: str | Path) -> list[dict[str, Any]]:
    repaired_pages: list[dict[str, Any]] = []
    for index, page in enumerate(pages, start=1):
        text = str(page.get("text") or "")
        if not is_unreadable_pdf_text(text):
            repaired_pages.append(page)
            continue
        page_number = int(page.get("page_number") or index)
        ocr_text = ocr_pdf_page_text(file_path, page_number=page_number)
        if not ocr_text or is_unreadable_pdf_text(ocr_text):
            raise ValidationError(
                f"OCR fallback did not produce readable text from {Path(file_path).name} page {page_number}"
            )
        repaired = dict(page)
        repaired["text"] = ocr_text
        repaired_pages.append(repaired)
    return repaired_pages


def validate_indexable_pdf_pages(pages: list[dict[str, Any]], *, file_path: str | Path) -> None:
    bad_pages = [
        int(page.get("page_number") or index)
        for index, page in enumerate(pages, start=1)
        if is_unreadable_pdf_text(str(page.get("text") or ""))
    ]
    if bad_pages:
        page_list = ", ".join(str(page) for page in bad_pages[:5])
        suffix = "..." if len(bad_pages) > 5 else ""
        raise ValidationError(
            f"unreadable PDF text extracted from {Path(file_path).name} on page(s): {page_list}{suffix}. "
            "Please provide a PDF with a valid text layer or run OCR before indexing."
        )


def split_text_to_chunks(text: str, *, chunk_size: int = 1000, overlap: int = 120) -> list[str]:
    clean = "\n".join(line.strip() for line in str(text or "").splitlines() if line.strip())
    if not clean:
        return []
    safe_chunk_size = max(1, int(chunk_size or 1000))
    safe_overlap = max(0, min(int(overlap or 0), safe_chunk_size - 1))
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + safe_chunk_size)
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(clean):
            break
        start = max(0, end - safe_overlap)
    return chunks


def split_text_by_headings(text: str, *, chunk_size: int = 1000, overlap: int = 120) -> list[tuple[str, str | None]]:
    """Split text into (chunk_text, heading_title) pairs using heading boundaries.

    Extracts headings from the text and splits at heading positions. Each heading
    creates a new section titled by that heading. Sections larger than chunk_size
    are further split with overlap.
    """
    headings = _extract_pdf_headings(text)
    clean = "\n".join(line.strip() for line in str(text or "").splitlines() if line.strip())
    if not clean:
        return []

    if not headings:
        # Fall back to size-based only
        return [(c, None) for c in split_text_to_chunks(clean, chunk_size=chunk_size, overlap=overlap)]

    # Build section boundaries from heading paragraph indices
    lines = clean.splitlines()
    heading_positions: list[tuple[int, str]] = []  # (line_index, heading_text)
    for h in headings:
        idx = h.get("paragraph_index", 0)
        if 0 <= idx < len(lines):
            heading_positions.append((idx, h.get("text", "")))

    heading_positions.sort(key=lambda x: x[0])

    # Split lines into sections at heading boundaries
    sections: list[tuple[str, str | None]] = []
    current_heading: str | None = None
    section_start = 0

    for boundary_idx, heading_text in heading_positions:
        if boundary_idx > section_start:
            section_text = "\n".join(lines[section_start:boundary_idx]).strip()
            if section_text:
                sections.append((section_text, current_heading))
        section_start = boundary_idx
        current_heading = heading_text

    # Last section after the final heading
    if section_start < len(lines):
        section_text = "\n".join(lines[section_start:]).strip()
        if section_text:
            sections.append((section_text, current_heading))

    # Further split large sections by size
    result: list[tuple[str, str | None]] = []
    for section_text, heading_title in sections:
        if len(section_text) <= chunk_size:
            result.append((section_text, heading_title))
        else:
            for sub_chunk in split_text_to_chunks(section_text, chunk_size=chunk_size, overlap=overlap):
                result.append((sub_chunk, heading_title))

    return result


def split_text_by_page(text: str) -> list[str]:
    """Return the full page text as a single chunk (one-chunk-per-page strategy)."""
    clean = "\n".join(line.strip() for line in str(text or "").splitlines() if line.strip())
    return [clean] if clean else []


def chunk_page_text(
    text: str,
    *,
    chunk_strategy: str = "heading_then_size",
    chunk_size: int = 1000,
    overlap: int = 120,
) -> list[dict[str, Any]]:
    """Split page text into chunks with strategy selection.

    Returns list of {"text": str, "section_title": str | None} dicts.
    """
    strategy = str(chunk_strategy or "heading_then_size").strip().lower()
    if strategy in ("page", "per_page"):
        chunks = split_text_by_page(text)
        return [{"text": c, "section_title": None} for c in chunks]
    if strategy in ("fixed_size", "fixed-size"):
        chunks = split_text_to_chunks(text, chunk_size=chunk_size, overlap=overlap)
        return [{"text": c, "section_title": None} for c in chunks]
    # Default: heading_then_size
    pairs = split_text_by_headings(text, chunk_size=chunk_size, overlap=overlap)
    return [{"text": c[0], "section_title": c[1]} for c in pairs]


def build_point_id(standard_no: str, *, page_number: int, chunk_index: int) -> str:
    safe_standard = re.sub(r"[^A-Za-z0-9]+", "-", str(standard_no or "").strip()).strip("-")
    return f"{safe_standard}-p{int(page_number)}-c{int(chunk_index)}"


def build_title(meta: dict[str, Any], *, page_number: int, chunk_index: int) -> str:
    return f"{meta['standard_no']} {meta['standard_name']} 第{page_number}页 第{chunk_index}段"


def build_index_docs(
    *,
    library_id: str,
    document_id: str,
    file_path: str | Path,
    meta: dict[str, Any],
    pages: list[dict[str, Any]],
    org_id: str | None = None,
    rag_space_id: str | None = None,
    chunk_size: int = 1000,
    overlap: int = 120,
    chunk_strategy: str = "heading_then_size",
) -> list[dict[str, Any]]:
    path = Path(file_path)
    pages = repair_unreadable_pdf_pages_with_ocr(pages, file_path=path)
    validate_indexable_pdf_pages(pages, file_path=path)
    docs: list[dict[str, Any]] = []
    for page in pages:
        page_number = int(page.get("page_number") or 1)
        page_chunks = chunk_page_text(
            str(page.get("text") or ""),
            chunk_strategy=chunk_strategy,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        for chunk_index, chunk_info in enumerate(page_chunks, start=1):
            chunk_text = chunk_info["text"]
            section_title = chunk_info.get("section_title")
            point_id = build_point_id(str(meta["standard_no"]), page_number=page_number, chunk_index=chunk_index)
            title = (
                f"{meta['standard_no']} {meta['standard_name']} {section_title} 第{page_number}页 第{chunk_index}段"
                if section_title
                else build_title(meta, page_number=page_number, chunk_index=chunk_index)
            )
            payload = {
                **meta,
                "org_id": org_id,
                "rag_space_id": rag_space_id,
                "library_id": library_id,
                "document_id": document_id,
                "file_name": path.name,
                "file_path": str(path).replace("\\", "/"),
                "page_number": page_number,
                "chunk_index": chunk_index,
            }
            if section_title:
                payload["section_title"] = section_title
            docs.append(
                {
                    "id": point_id,
                    "title": title,
                    "text": chunk_text,
                    "source": str(meta["standard_no"]),
                    "payload": payload,
                }
            )
    return docs


class StandardPdfImporter:
    def __init__(self, *, org_id: str | None = None, indexer: KnowledgeIndexer | None = None, retriever: Retriever | None = None):
        self._org_id = org_id
        self._indexer = indexer or KnowledgeIndexer(org_id=org_id)
        self._retriever = retriever or Retriever(org_id=org_id)

    def scan_directory(
        self,
        root_dir: str | Path,
        *,
        file_glob: str = "*.pdf",
        fallback_domain: str | None = None,
        fallback_product_category: str | None = None,
    ) -> list[dict[str, Any]]:
        root = Path(root_dir)
        if not root.exists() or not root.is_dir():
            raise ValidationError(f"pdf root directory not found: {root}")
        documents = []
        for path in sorted(root.rglob(file_glob or "*.pdf")):
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            meta = resolve_standard_meta(path, fallback_domain=fallback_domain, fallback_product_category=fallback_product_category)
            documents.append(
                {
                    **meta,
                    "file_name": path.name,
                    "file_path": str(path).replace("\\", "/"),
                    "file_hash": sha256_file(path),
                    "file_size": path.stat().st_size,
                    "import_status": "pending",
                }
            )
        return documents

    async def index_document(
        self,
        *,
        library_id: str,
        document_id: str,
        file_path: str | Path,
        meta: dict[str, Any],
        rag_space_id: str | None = None,
        chunk_size: int = 1000,
        overlap: int = 120,
        chunk_strategy: str = "heading_then_size",
    ) -> dict[str, Any]:
        pages, page_count = extract_pdf_pages(file_path)
        if not pages:
            raise ValidationError(f"document has no indexable text: {Path(file_path).name}")
        docs = build_index_docs(
            library_id=library_id,
            document_id=document_id,
            file_path=file_path,
            meta=meta,
            pages=pages,
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            chunk_size=chunk_size,
            overlap=overlap,
            chunk_strategy=chunk_strategy,
        )
        result = await self._indexer.index(docs)
        return {"docs": docs, "page_count": page_count, **result}

    async def retrieve(self, *, query: str, top_k: int, payload_filter: dict[str, Any] | None = None) -> dict[str, Any]:
        started_at = perf_counter()
        docs = await self._retriever.retrieve(query, top_k=top_k, payload_filter=payload_filter)
        return {
            "hits": docs,
            "hit_count": len(docs),
            "candidate_count": len(docs),
            "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        }

    async def delete_document_points(self, *, document_id: str, library_id: str) -> None:
        await self._indexer.delete_by_filter(
            {
                "org_id": self._org_id,
                "document_id": document_id,
                "library_id": library_id,
            }
        )

    async def delete_library_points(self, *, library_id: str) -> None:
        await self._indexer.delete_by_filter(
            {
                "org_id": self._org_id,
                "library_id": library_id,
            }
        )
