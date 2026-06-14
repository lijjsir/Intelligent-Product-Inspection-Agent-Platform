"""SessionMemoryVectorService — session-local semantic recall via Qdrant."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

SESSION_MEMORY_COLLECTION = "piap_session_memory"


class SessionMemoryVectorService:
    def __init__(self, embedder_factory, org_id: str, user_id: str | None = None):
        self._embed = embedder_factory
        self._org_id = org_id
        self._user_id = user_id

    async def upsert_message(
        self, *, org_id: str, user_id: str, session_id: str,
        message_id: str, seq_no: int, role: str, content: str,
    ) -> None:
        """Index a chat message for session-local semantic recall."""
        from app.services.memory_vector_service import MemoryVectorService

        vector_svc = MemoryVectorService(
            collection=SESSION_MEMORY_COLLECTION,
            embedder_factory=self._embed,
            org_id=org_id,
            user_id=user_id,
        )
        embedding = await self._embed(content[:2000])
        await vector_svc.upsert_memory(
            memory_id=f"session_msg_{message_id}",
            org_id=org_id,
            user_id=user_id,
            memory_type="session_message",
            status="active",
            summary=content[:500],
            vector=embedding,
            extra_payload={
                "session_id": session_id,
                "message_id": message_id,
                "seq_no": seq_no,
                "role": role,
                "summary": content[:500],
            },
        )

    async def search_session(
        self, *, org_id: str, user_id: str, session_id: str,
        query: str, before_seq_no: int, top_k: int = 5,
    ) -> list[dict]:
        """Search session messages semantically, returning snippets before a given seq_no."""
        from app.services.memory_vector_service import MemoryVectorService

        vector_svc = MemoryVectorService(
            collection=SESSION_MEMORY_COLLECTION,
            embedder_factory=self._embed,
            org_id=org_id,
            user_id=user_id,
        )
        embedding = await self._embed(query[:2000])
        results = await vector_svc.search(
            vector=embedding,
            filter_conditions={
                "must": [
                    {"key": "session_id", "match": {"value": session_id}},
                    {"key": "seq_no", "range": {"lt": before_seq_no}},
                ]
            },
            top_k=top_k,
        )
        return [
            {
                "role": r.get("payload", {}).get("role", ""),
                "content": r.get("payload", {}).get("summary", ""),
                "seq_no": r.get("payload", {}).get("seq_no", 0),
                "score": r.get("score", 0.0),
            }
            for r in results
        ]
