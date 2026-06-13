from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.memory import MemorySyncOutbox
from app.repositories.memory_repo import MemorySyncOutboxRepository


class FakeResult:
    def __init__(self, items=None, one=None, rowcount=0):
        self._items = items or []
        self._one = one
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return self._items

    def scalar_one_or_none(self):
        return self._one


class FakeSession:
    def __init__(self):
        self.added = []
        self.statements = []

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        return None

    async def execute(self, stmt):
        self.statements.append(stmt)
        return FakeResult(items=[SimpleNamespace(id="out-1", status="pending")], rowcount=1)


@pytest.mark.asyncio
async def test_memory_sync_outbox_repository_creates_pending_record():
    session = FakeSession()
    repo = MemorySyncOutboxRepository(session, "org-1")

    outbox = await repo.create_pending(
        memory_id="mem-1",
        action="upsert_memory",
        target_backend="qdrant",
        payload={"summary": "stable lesson"},
        trace_id="trace-1",
    )

    assert isinstance(outbox, MemorySyncOutbox)
    assert outbox.status == "pending"
    assert outbox.retry_count == 0
    assert outbox.payload_json == {"summary": "stable lesson"}
    assert session.added == [outbox]


@pytest.mark.asyncio
async def test_memory_sync_outbox_repository_claims_pending_batch():
    session = FakeSession()
    repo = MemorySyncOutboxRepository(session, "org-1")

    items = await repo.claim_pending(limit=10, max_retries=3)

    assert items[0].id == "out-1"
    assert session.statements
