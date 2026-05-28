"""Qdrant retriever for paper template clauses."""
from __future__ import annotations

from typing import Any

import httpx

from agent.rag.embedder import Embedder
from app.core.config import settings


class PaperTemplateClauseRetriever:
    def __init__(self, *, trace_id: str | None = None, task_id: str | None = None, org_id: str | None = None) -> None:
        self._embedder = Embedder(
            trace_id=trace_id,
            task_id=task_id,
            org_id=org_id,
            allow_pseudo_fallback=False,
        )
        self._qdrant_url = settings.qdrant_url.rstrip("/")
        self._qdrant_api_key = settings.qdrant_api_key
        self._collection = settings.paper_template_qdrant_collection

    async def retrieve_for_issues(
        self,
        *,
        template_id: str,
        issues: list[dict[str, Any]],
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        """Search Qdrant for template clauses most relevant to the given issues.

        Returns empty list when the collection is empty or does not exist yet.
        """
        if not issues:
            return []

        query_text = _build_retrieval_query(issues)
        vector = await self._embedder.embed(query_text)

        if not vector:
            return []

        payload: dict[str, Any] = {
            "vector": vector,
            "limit": top_k,
            "with_payload": True,
            "filter": {
                "must": [
                    {"key": "template_id", "match": {"value": template_id}}
                ]
            },
        }

        headers: dict[str, str] = {}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key

        try:
            async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
                response = await client.post(
                    f"{self._qdrant_url}/collections/{self._collection}/points/search",
                    json=payload,
                    headers=headers,
                )
                if response.status_code in {400, 404}:
                    return []
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError:
            return []

        points = data.get("result") or []
        return [
            {
                "clause_id": p["payload"].get("clause_id", ""),
                "section_title": p["payload"].get("section_title", ""),
                "clause_title": p["payload"].get("clause_title", ""),
                "text": p["payload"].get("clause_text", ""),
                "category": p["payload"].get("category", ""),
                "target_type": p["payload"].get("target_type", ""),
                "rule_codes": p["payload"].get("rule_codes", []),
                "severity": p["payload"].get("severity", ""),
                "source_file_name": p["payload"].get("source_file_name", ""),
                "score": float(p.get("score", 0.0)),
            }
            for p in points
            if p.get("payload")
        ]


def _build_retrieval_query(issues: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for issue in issues:
        parts.append(f"{issue.get('code', '')} {issue.get('title', '')} {issue.get('category', '')}")
        expected = issue.get("expected")
        if isinstance(expected, dict):
            parts.append(" ".join(str(v) for v in expected.values()))
    return " ".join(parts)[:2000]
