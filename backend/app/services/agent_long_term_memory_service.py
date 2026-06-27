"""Long-term private memory for one business agent, stored in Qdrant."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from agent.rag.embedder import Embedder
from app.services.memory_vector_service import (
    AGENT_LOCAL_MEMORY_COLLECTION,
    MemoryVectorService,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentLongTermMemoryService:
    """Read and write tenant- and agent-isolated long-term experience."""

    def __init__(
        self,
        *,
        org_id: str,
        user_id: str | None = None,
        trace_id: str | None = None,
        vector_service: MemoryVectorService | None = None,
    ) -> None:
        self._org_id = str(org_id or "").strip()
        if not self._org_id:
            raise ValueError("org_id is required for agent long-term memory")
        self._user_id = user_id
        self._trace_id = trace_id
        self._vector = vector_service or self._build_vector_service()

    def _build_vector_service(self) -> MemoryVectorService:
        async def embedder_factory(text: str) -> list[float]:
            embedder = Embedder(
                org_id=self._org_id,
                user_id=self._user_id,
                trace_id=self._trace_id,
                allow_pseudo_fallback=False,
            )
            return await embedder.embed(text)

        return MemoryVectorService(
            collection=AGENT_LOCAL_MEMORY_COLLECTION,
            embedder_factory=embedder_factory,
            org_id=self._org_id,
            user_id=self._user_id,
            trace_id=self._trace_id,
        )

    async def ensure_collection(self, vector_size: int = 1536) -> None:
        await self._vector.ensure_collection(vector_size=vector_size)

    async def write(
        self,
        *,
        agent_id: str,
        summary: str,
        product_line: str | None = None,
        task_type: str | None = None,
        confidence: float = 0.5,
        trust_score: float = 0.5,
        shareable: bool = False,
        share_reason: str | None = None,
        target_agents: list[str] | None = None,
        share_value_score: float = 0.0,
        expires_at: str | None = None,
        memory_id: str | None = None,
        vector: list[float] | None = None,
    ) -> dict[str, Any]:
        owner = str(agent_id or "").strip()
        text = str(summary or "").strip()
        if not owner:
            raise ValueError("agent_id is required for agent long-term memory")
        if not text:
            raise ValueError("summary is required for agent long-term memory")

        now = _utc_now()
        resolved_expires_at = expires_at or (now + timedelta(days=90)).isoformat()
        resolved_memory_id = memory_id or f"alm_{uuid4().hex}"
        payload = {
            "summary": text[:1000],
            "agent_id": owner,
            "task_type": str(task_type or ""),
            "shareable": bool(shareable),
            "share_reason": str(share_reason or ""),
            "target_agents": list(target_agents or []),
            "share_value_score": max(0.0, min(1.0, float(share_value_score))),
            "created_at": now.isoformat(),
        }
        await self._vector.upsert_memory(
            memory_id=resolved_memory_id,
            org_id=self._org_id,
            user_id=str(self._user_id or ""),
            memory_type="agent_experience",
            status="active",
            summary=text,
            vector=vector,
            trust_score=max(0.0, min(1.0, float(trust_score))),
            confidence=max(0.0, min(1.0, float(confidence))),
            expires_at=resolved_expires_at,
            product_line=str(product_line or ""),
            extra_payload=payload,
        )
        return {
            "memory_id": resolved_memory_id,
            "org_id": self._org_id,
            "user_id": self._user_id,
            "memory_type": "agent_experience",
            "status": "active",
            "confidence": max(0.0, min(1.0, float(confidence))),
            "trust_score": max(0.0, min(1.0, float(trust_score))),
            "expires_at": resolved_expires_at,
            "product_line": str(product_line or ""),
            **payload,
        }

    async def search(
        self,
        *,
        agent_id: str,
        query: str,
        product_line: str | None = None,
        task_type: str | None = None,
        top_k: int = 5,
        vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        clauses = self._base_filter(agent_id)
        if product_line:
            clauses.append(
                {"key": "product_line", "match": {"value": product_line}}
            )
        if task_type:
            clauses.append({"key": "task_type", "match": {"value": task_type}})
        results = await self._vector.search(
            query=query,
            vector=vector,
            top_k=top_k,
            filter_conditions={"must": clauses},
        )
        return self._active_unexpired(results)

    async def list_shareable(
        self,
        *,
        agent_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = self._base_filter(agent_id)
        clauses.append({"key": "shareable", "match": {"value": True}})
        results = await self._vector.scroll(
            filter_conditions={"must": clauses},
            limit=limit,
        )
        return [
            dict(item.get("payload") or {})
            for item in self._active_unexpired(results)
        ]

    async def delete(self, memory_id: str) -> None:
        await self._vector.delete_memory(memory_id)

    def _base_filter(self, agent_id: str) -> list[dict[str, Any]]:
        owner = str(agent_id or "").strip()
        if not owner:
            raise ValueError("agent_id is required for agent long-term memory")
        return [
            {"key": "org_id", "match": {"value": self._org_id}},
            {"key": "agent_id", "match": {"value": owner}},
            {"key": "status", "match": {"value": "active"}},
        ]

    @staticmethod
    def _active_unexpired(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = _utc_now()
        active: list[dict[str, Any]] = []
        for item in results:
            payload = dict(item.get("payload") or {})
            expires_at = str(payload.get("expires_at") or "").strip()
            if expires_at:
                try:
                    expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if expires <= now:
                        continue
                except ValueError:
                    continue
            active.append(item)
        return active
