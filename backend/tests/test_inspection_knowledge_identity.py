from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from agent.subgraphs.inspection_task.nodes import knowledge


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", ["task-owner", None])
async def test_legacy_task_knowledge_preserves_identity_without_inventing_one(monkeypatch, user_id):
    @asynccontextmanager
    async def session():
        yield object()

    retrieval = AsyncMock(return_value={"hits": [], "source_count": 0})
    monkeypatch.setattr(knowledge, "get_session", session)
    monkeypatch.setattr(knowledge, "resolve_and_search_system_rag", retrieval)
    state = {"org_id": "org-1", "user_id": user_id, "selected_rag_space_id": "selected"}
    result = await knowledge.run_knowledge(state)
    assert retrieval.call_args.kwargs["user_id"] == user_id
    assert result["knowledge_docs"] == []
    assert not result.get("runtime_errors")
