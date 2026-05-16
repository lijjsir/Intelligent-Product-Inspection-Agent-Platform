from __future__ import annotations

import re
from collections import Counter
from time import perf_counter
from typing import Any

from agent.tools.file_parsers import parse_file_content
from app.repositories.rag_space_repo import RagDocumentRepository, RagNodeRepository, RagSpaceRepository
from app.services.file_storage_service import FileStorageService


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(str(text or ""))]


def _chunk_text(text: str, chunk_size: int = 380) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw) if part.strip()]
    if not paragraphs:
        paragraphs = [raw]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
            continue
        for start in range(0, len(paragraph), chunk_size):
            chunks.append(paragraph[start : start + chunk_size].strip())
        current = ""
    if current:
        chunks.append(current)
    return chunks[:24]


def _score_chunk(query_tokens: list[str], chunk: str) -> float:
    if not query_tokens:
        return 0.0
    chunk_tokens = _tokenize(chunk)
    if not chunk_tokens:
        return 0.0
    query_counter = Counter(query_tokens)
    chunk_counter = Counter(chunk_tokens)
    overlap = sum(min(chunk_counter[token], count) for token, count in query_counter.items())
    if overlap <= 0:
        return 0.0
    return round(overlap / max(len(query_tokens), 1), 4)


class RagRetrievalService:
    def __init__(self, session, *, org_id: str, user_id: str | None = None):
        self._session = session
        self._org_id = org_id
        self._user_id = user_id
        self._spaces = RagSpaceRepository(session)
        self._nodes = RagNodeRepository(session)
        self._documents = RagDocumentRepository(session)
        self._storage = FileStorageService()

    async def search(self, *, rag_space_id: str | None, query: str, top_k: int = 4) -> dict[str, Any]:
        started_at = perf_counter()
        if not rag_space_id:
            return {
                "rag_space_id": None,
                "rag_space_name": None,
                "hits": [],
                "hit_count": 0,
                "latency_ms": 0.0,
            }

        space = await self._spaces.get(
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            owner_user_id=self._user_id,
        )
        if not space:
            return {
                "rag_space_id": rag_space_id,
                "rag_space_name": None,
                "hits": [],
                "hit_count": 0,
                "latency_ms": round((perf_counter() - started_at) * 1000, 2),
            }

        documents = await self._documents.list_for_space(
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            owner_user_id=self._user_id,
            limit=20,
        )
        nodes = await self._nodes.list_for_space(
            org_id=self._org_id,
            rag_space_id=rag_space_id,
            owner_user_id=self._user_id,
        )
        node_map = {str(node.id): node for node in nodes}
        query_tokens = _tokenize(query)
        hits: list[dict[str, Any]] = []
        for document in documents:
            payload = self._storage.file_bytes_from_url(str(document.file_url))
            if payload is None:
                continue
            content, _content_type = payload
            parsed = parse_file_content(str(document.file_name), content)
            text = str(parsed.get("text") or "").strip()
            node = node_map.get(str(document.node_id))
            for index, chunk in enumerate(_chunk_text(text), start=1):
                score = _score_chunk(query_tokens, chunk)
                if score <= 0:
                    continue
                hits.append(
                    {
                        "id": f"{document.id}:{index}",
                        "title": str(document.file_name),
                        "source": node.full_path if node is not None else str(document.file_name),
                        "quote": chunk[:220],
                        "score": score,
                        "file_url": str(document.file_url),
                    }
                )

        hits.sort(key=lambda item: (item["score"], item["title"]), reverse=True)
        selected = hits[: max(1, top_k)]
        return {
            "rag_space_id": str(space.id),
            "rag_space_name": str(space.name),
            "hits": selected,
            "hit_count": len(selected),
            "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        }
