from __future__ import annotations

import hashlib
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from agent.rag.knowledge_indexer import KnowledgeIndexer
from agent.rag.retriever import Retriever
from agent.tools.file_parsers import parse_file_content
from app.core.exceptions import ValidationError
from app.services.standard_meta_registry import STANDARD_META_REGISTRY


STANDARD_NO_PATTERN = re.compile(r"(?P<number>\d+(?:\.\d+)?)[-_ ](?P<year>\d{4})", re.I)


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
    return pages, int(parsed.get("page_count") or len(raw_pages) or len(pages))


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
) -> list[dict[str, Any]]:
    path = Path(file_path)
    docs: list[dict[str, Any]] = []
    for page in pages:
        page_number = int(page.get("page_number") or 1)
        for chunk_index, chunk_text in enumerate(
            split_text_to_chunks(str(page.get("text") or ""), chunk_size=chunk_size, overlap=overlap),
            start=1,
        ):
            point_id = build_point_id(str(meta["standard_no"]), page_number=page_number, chunk_index=chunk_index)
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
            docs.append(
                {
                    "id": point_id,
                    "title": build_title(meta, page_number=page_number, chunk_index=chunk_index),
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
