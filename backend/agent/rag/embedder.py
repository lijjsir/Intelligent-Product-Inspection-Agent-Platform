from __future__ import annotations

import hashlib
import math
from typing import Any

from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from app.services.model_config_service import ModelConfigService
from infra.cache.memory_cache import _embedding_cache, stable_cache_key
from infra.database.session import get_session


EMBEDDING_MODEL_TYPES = {"embedding", "embed", "text_embedding"}


class EmbeddingModelNotConfigured(RuntimeError):
    pass


class Embedder:
    def __init__(
        self,
        *,
        trace_id: str | None = None,
        task_id: str | None = None,
        org_id: str | None = None,
        runtime_models: list[dict[str, Any]] | None = None,
    ) -> None:
        self._trace_id = trace_id
        self._task_id = None if task_id is None else str(task_id)
        self._org_id = None if org_id is None else str(org_id)
        self._runtime_models = runtime_models
        self._llm: LLMClient | None = None

    async def embed(self, text: str) -> list[float]:
        normalized_text = " ".join(str(text or "").strip().lower().split())
        runtime = await self._resolve_runtime()
        cache_key = stable_cache_key("embedding", runtime.get("model_id"), normalized_text)
        cached = _embedding_cache.get(cache_key)
        if cached is not None:
            return list(cached)
        try:
            llm = await self._client(runtime)
            embedding = await llm.embed(
                text,
                observation_name="rag.query_embedding",
                observation_metadata={"component": "retriever"},
            )
        except EmbeddingModelNotConfigured:
            raise
        except Exception:
            embedding = self._pseudo_embed(normalized_text)
        _embedding_cache.set(cache_key, list(embedding), ttl_seconds=1800)
        return embedding

    async def _client(self, runtime: dict[str, Any] | None = None) -> LLMClient:
        if self._llm is not None:
            return self._llm

        runtime = runtime or await self._resolve_runtime()
        model_id = str(runtime.get("model_id") or "")
        self._llm = LLMClient(
            api_key=runtime.get("api_key"),
            base_url=runtime.get("base_url"),
            model_id=model_id,
            embed_model=model_id,
            trace_id=self._trace_id,
            task_id=self._task_id,
            org_id=self._org_id,
            provider=str(runtime.get("provider") or ""),
            input_price_per_million=runtime.get("input_price_per_million"),
            output_price_per_million=runtime.get("output_price_per_million"),
        )
        return self._llm

    async def _resolve_runtime(self) -> dict[str, Any]:
        runtime_models = self._runtime_models
        if runtime_models is None:
            async with get_session() as session:
                runtime_models = await ModelConfigService(session, self._org_id).list_runtime_models()

        runtime = await LLMGateway().select_runtime(
            runtime_models,
            model_types=EMBEDDING_MODEL_TYPES,
        )
        if not runtime:
            raise EmbeddingModelNotConfigured("no active embedding model configured in model config page")
        return runtime

    @staticmethod
    def _pseudo_embed(text: str, dims: int = 256) -> list[float]:
        vec = [0.0] * dims
        words = text.lower().split()
        if not words:
            return vec
        for wi, word in enumerate(words):
            digest = hashlib.sha256(f"{wi}:{word}".encode()).digest()
            for i in range(0, len(digest), 2):
                idx = (i // 2) % dims
                val = (digest[i] * 256 + digest[i + 1]) / 65535.0
                vec[idx] += val / len(words)
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec
