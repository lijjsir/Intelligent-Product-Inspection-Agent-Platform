from types import SimpleNamespace

import pytest
from sqlalchemy.exc import MultipleResultsFound

from app.repositories.chat_repo import ChatMessageRepository, ChatOpsRepository


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class FakeResult:
    def __init__(self, items):
        self._items = items

    def scalar_one_or_none(self):
        if len(self._items) > 1:
            raise MultipleResultsFound("Multiple rows were found when one or none was required")
        return self._items[0] if self._items else None

    def scalars(self):
        return FakeScalarResult(self._items)


class FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.added = []
        self.flush_count = 0

    async def execute(self, _stmt):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1


class CaptureSession:
    def __init__(self):
        self.statement = None

    async def execute(self, stmt):
        self.statement = stmt
        return FakeResult([])


@pytest.mark.asyncio
async def test_chat_binding_tolerates_duplicate_existing_agents_and_routes():
    agents = [
        SimpleNamespace(
            id="agent-old",
            subgraph_key="chat",
            entry_graph="MemoryManagerGraph",
            graph_version="v1",
        ),
        SimpleNamespace(
            id="agent-duplicate",
            subgraph_key="legacy_quality",
            entry_graph="QualityAgentRootGraph",
            graph_version="v1",
        ),
    ]
    routes = [
        SimpleNamespace(agent_id="agent-old"),
        SimpleNamespace(agent_id="agent-duplicate"),
    ]
    session = FakeSession([FakeResult(agents), FakeResult(routes)])

    await ChatOpsRepository(session, "org-1").ensure_chat_binding()

    assert session.added == []
    assert routes[0].agent_id == "agent-old"


@pytest.mark.asyncio
async def test_list_assistant_for_org_allows_global_scope_without_org_filter():
    session = CaptureSession()

    await ChatMessageRepository(session).list_assistant_for_org(None)

    compiled = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "chat_messages.org_id IS NULL" not in compiled
