from unittest.mock import AsyncMock
import pytest
from agent.rag.embedder import Embedder
from infra.cache.memory_cache import _embedding_cache


@pytest.mark.asyncio
async def test_strict_published_embedding_cannot_reuse_cached_pseudo_vector():
    _embedding_cache.clear()
    permissive=Embedder(allow_pseudo_fallback=True)
    strict=Embedder(allow_pseudo_fallback=False)
    class FailedClient:
        async def embed(self,*args,**kwargs): raise RuntimeError("isolated embedding outage")
    for embedder in [permissive,strict]:
        embedder._resolve_runtime=AsyncMock(return_value={"model_id":"fixture-model"})
        embedder._client=AsyncMock(return_value=FailedClient())
    assert await permissive.embed("fixture clause")
    with pytest.raises(RuntimeError,match="outage"):
        await strict.embed("fixture clause")
    _embedding_cache.clear()
