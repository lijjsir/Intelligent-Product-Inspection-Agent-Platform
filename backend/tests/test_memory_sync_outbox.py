from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.memory import MemorySyncOutbox
from app.repositories.memory_repo import MemorySyncOutboxRepository
from worker.celery_app import celery_app
from worker.tasks import memory_sync_outbox_task


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
    def __init__(self, items=None):
        self.added = []
        self.statements = []
        self.items = items or [SimpleNamespace(id="out-1", status="pending")]

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        return None

    async def execute(self, stmt):
        self.statements.append(stmt)
        return FakeResult(items=self.items, rowcount=1)


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


@pytest.mark.asyncio
async def test_memory_sync_outbox_repository_lists_orgs_with_pending_rows():
    session = FakeSession(items=["org-1", "org-2"])

    org_ids = await MemorySyncOutboxRepository.list_pending_org_ids(
        session,
        max_retries=3,
    )

    assert org_ids == ["org-1", "org-2"]
    assert session.statements


@pytest.mark.asyncio
async def test_memory_sync_outbox_dispatcher_queues_each_pending_org(monkeypatch):
    queued: list[str] = []

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_list_pending_org_ids(session, *, max_retries):
        assert max_retries == 5
        return ["org-1", "org-2"]

    monkeypatch.setattr(memory_sync_outbox_task, "get_session", lambda: FakeSessionContext())
    monkeypatch.setattr(
        memory_sync_outbox_task.MemorySyncOutboxRepository,
        "list_pending_org_ids",
        fake_list_pending_org_ids,
    )
    monkeypatch.setattr(
        memory_sync_outbox_task.process_memory_sync_outbox,
        "delay",
        lambda org_id: queued.append(org_id),
    )
    monkeypatch.setattr(memory_sync_outbox_task.settings, "memory_sync_outbox_max_retries", 5)

    result = await memory_sync_outbox_task._dispatch_memory_sync_outbox()

    assert result == {"orgs": 2, "queued": ["org-1", "org-2"]}
    assert queued == ["org-1", "org-2"]


def test_memory_sync_outbox_dispatcher_is_scheduled_by_beat():
    schedule = celery_app.conf.beat_schedule

    assert schedule["memory-sync-outbox-dispatch"]["task"] == (
        "worker.tasks.memory_sync_outbox_task.dispatch_memory_sync_outbox"
    )
