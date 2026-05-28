"""Index paper template writing guides into MySQL + Qdrant.

Lifecycle: MinIO (object storage) -> parse -> split clauses -> MySQL -> embed -> Qdrant.
All operations are idempotent — re-running produces the same result without duplicates.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from agent.rag.embedder import Embedder
from agent.tools.file_parsers import parse_file_content
from agent.tools.paper_template_indexer import split_guide_into_clauses
from app.core.config import settings
from app.models.paper_template import PaperTemplate, PaperTemplateClause
from app.repositories.paper_template_repo import (
    PaperTemplateClauseRepository,
    PaperTemplateRepository,
)

logger = logging.getLogger(__name__)


class PaperTemplateIndexService:
    def __init__(self, session: AsyncSession, *, org_id: str | None = None):
        self._session = session
        self._template_repo = PaperTemplateRepository(session)
        self._clause_repo = PaperTemplateClauseRepository(session)
        self._embedder = Embedder(org_id=org_id, allow_pseudo_fallback=False)
        self._qdrant_url = settings.qdrant_url.rstrip("/")
        self._qdrant_api_key = settings.qdrant_api_key
        self._collection = settings.paper_template_qdrant_collection

    async def is_indexed(self, *, template_id: str) -> bool:
        """Check whether a template already has clauses in MySQL."""
        existing = await self._template_repo.get_by_template_id(template_id)
        if existing is None:
            return False
        clauses = await self._clause_repo.list_by_template(template_id)
        return len(clauses) > 0

    async def index_template(
        self,
        *,
        template_id: str,
        template_name: str,
        guide_file_bytes: bytes,
        guide_file_name: str = "writing-guide.docx",
        school_name: str | None = None,
        degree_type: str | None = None,
        version: str | None = None,
        description: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Index a writing guide: parse, split, store in MySQL, embed into Qdrant.

        Idempotent by default — if the template is already indexed, returns immediately
        with ``status: "already_indexed"``. Pass ``force=True`` to re-index.
        """
        if not force and await self.is_indexed(template_id=template_id):
            clauses = await self._clause_repo.list_by_template(template_id)
            return {
                "template_id": template_id,
                "clause_count": len(clauses),
                "status": "already_indexed",
            }

        # 1. Parse the writing guide
        parsed = parse_file_content(guide_file_name, guide_file_bytes)

        # 2. Split into clauses
        clauses = split_guide_into_clauses(
            parsed,
            template_id=template_id,
            source_file_name=guide_file_name,
        )

        # 3. Write template metadata to MySQL (upsert = idempotent)
        template = PaperTemplate(
            template_id=template_id,
            template_name=template_name,
            school_name=school_name,
            degree_type=degree_type,
            version=version,
            description=description,
        )
        await self._template_repo.upsert_template(template)

        # 4. Replace old clauses with new ones
        await self._clause_repo.delete_by_template(template_id)
        for clause_data in clauses:
            clause = PaperTemplateClause(
                template_id=template_id,
                clause_id=clause_data["clause_id"],
                section_title=clause_data.get("section_title", ""),
                clause_title=clause_data.get("clause_title", ""),
                clause_text=clause_data["clause_text"],
                normalized_text=clause_data.get("normalized_text", ""),
                target_type=clause_data.get("target_type", ""),
                category=clause_data.get("category", ""),
                rule_codes=clause_data.get("rule_codes", []),
                source_file_name=guide_file_name,
                source_hash=clause_data.get("source_hash", ""),
            )
            await self._clause_repo.upsert_clause(clause)

        # 5. Vectorize and index into Qdrant (PUT = upsert by point id)
        points = []
        for clause_data in clauses:
            vector_text = clause_data.get("vector_text", clause_data["clause_text"])[:2000]
            try:
                vector = await self._embedder.embed(vector_text)
            except Exception:
                continue
            if not vector:
                continue
            points.append({
                "id": str(clause_data["clause_id"]),
                "vector": vector,
                "payload": {
                    "template_id": template_id,
                    "clause_id": clause_data["clause_id"],
                    "section_title": clause_data.get("section_title", ""),
                    "clause_title": clause_data.get("clause_title", ""),
                    "clause_text": clause_data["clause_text"],
                    "category": clause_data.get("category", ""),
                    "target_type": clause_data.get("target_type", ""),
                    "rule_codes": clause_data.get("rule_codes", []),
                    "severity": "medium",
                    "source_file_name": guide_file_name,
                },
            })

        if clauses and not points:
            await self._session.rollback()
            raise RuntimeError(
                "模板条款向量化失败：未找到可用的嵌入模型。"
                "请在模型配置页面添加 model_type=embedding 的模型，确保 is_active=1。"
                " 错误码: PAPER_TEMPLATE_EMBED_FAILED"
            )

        if points:
            vector_dim = len(points[0]["vector"])
            await self._ensure_qdrant_collection(vector_dim)
            await self._upsert_qdrant_points(points)

        await self._session.commit()
        logger.info(
            "paper template indexed template_id=%s clauses=%d qdrant_points=%d",
            template_id, len(clauses), len(points),
        )
        return {
            "template_id": template_id,
            "clause_count": len(clauses),
            "qdrant_points": len(points),
            "status": "indexed",
        }

    # ---- internal ----

    async def _ensure_qdrant_collection(self, vector_size: int) -> None:
        headers = {"Content-Type": "application/json"}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key
        payload = {"vectors": {"size": vector_size, "distance": "Cosine"}}
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            existing = await client.get(
                f"{self._qdrant_url}/collections/{self._collection}",
                headers=headers,
            )
            if existing.status_code == 200:
                data = existing.json()
                current_size = (
                    ((data.get("result") or {}).get("config") or {})
                    .get("params", {})
                    .get("vectors", {})
                    .get("size")
                )
                if int(current_size or 0) == int(vector_size):
                    return
                await client.delete(
                    f"{self._qdrant_url}/collections/{self._collection}",
                    headers=headers,
                )
            elif existing.status_code != 404:
                existing.raise_for_status()
            await client.put(
                f"{self._qdrant_url}/collections/{self._collection}",
                json=payload,
                headers=headers,
            )

    async def _upsert_qdrant_points(self, points: list[dict[str, Any]]) -> None:
        headers = {"Content-Type": "application/json"}
        if self._qdrant_api_key:
            headers["api-key"] = self._qdrant_api_key
        payload = {"points": points}
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            resp = await client.put(
                f"{self._qdrant_url}/collections/{self._collection}/points",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
