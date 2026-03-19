from __future__ import annotations

from agent.llm.client import LLMClient


class Embedder:
    def __init__(self) -> None:
        self._llm = LLMClient()

    async def embed(self, text: str) -> list[float]:
        return await self._llm.embed(text)
