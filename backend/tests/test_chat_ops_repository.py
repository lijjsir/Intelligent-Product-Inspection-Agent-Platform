from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import MultipleResultsFound

from app.models.chat import ChatMessage
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


@pytest.mark.asyncio
async def test_list_for_session_forces_compound_index_on_mysql():
    session = CaptureSession()

    await ChatMessageRepository(session).list_for_session(
        org_id="11111111-1111-1111-1111-111111111111",
        session_id="22222222-2222-2222-2222-222222222222",
        after_seq=0,
        limit=50,
    )

    compiled = str(session.statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "FORCE INDEX (idx_chat_messages_org_session_seq)" in compiled


def test_chat_message_declares_compound_indexes_for_session_pagination():
    indexes = {index.name: tuple(column.name for column in index.columns) for index in ChatMessage.__table__.indexes}

    assert indexes["idx_chat_messages_session_seq"] == ("session_id", "seq_no")
    assert indexes["idx_chat_messages_org_session_seq"] == ("org_id", "session_id", "seq_no")
