from __future__ import annotations

from agent.llm.client import LLMClient


class Embedder:
    def __init__(self, *, trace_id: str | None = None, task_id: str | None = None, org_id: str | None = None) -> None:
        self._llm = LLMClient(trace_id=trace_id, task_id=task_id, org_id=org_id, provider="volcengine")

    async def embed(self, text: str) -> list[float]:
        return await self._llm.embed(
            text,
            observation_name="rag.query_embedding",
            observation_metadata={"component": "retriever"},
        )
