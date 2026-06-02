from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_paper_review_worker_failure_writes_failed_assistant_message(monkeypatch):
    from worker.tasks import paper_review_chat_task as task_mod

    updates: list[dict] = []
    commits: list[bool] = []
    published: list[tuple[str, dict]] = []

    class FakeSession:
        async def commit(self):
            commits.append(True)

    class FakeSessionContext:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeChatMessageRepository:
        def __init__(self, _session):
            pass

        async def update_assistant_message(self, **kwargs):
            updates.append(kwargs)
            return SimpleNamespace()

    class FakeBroker:
        async def publish(self, session_id: str, event: dict):
            published.append((session_id, event))

    monkeypatch.setattr(task_mod, "get_session", lambda: FakeSessionContext())
    monkeypatch.setattr(task_mod, "ChatMessageRepository", FakeChatMessageRepository)
    monkeypatch.setattr(task_mod, "chat_stream_broker", FakeBroker())

    await task_mod._persist_paper_review_failure(
        {
            "org_id": "org-1",
            "session_id": "session-1",
            "assistant_message_id": "assistant-1",
            "workflow_run_id": "workflow-1",
        },
        RuntimeError("boom"),
    )

    assert commits == [True]
    assert updates[0]["org_id"] == "org-1"
    assert updates[0]["message_id"] == "assistant-1"
    assert updates[0]["message_type"] == "error"
    assert updates[0]["payload"]["status"] == "failed"
    assert updates[0]["payload"]["ui_schema"] == "paper_review_error_v1"
    assert updates[0]["payload"]["paper_review_error"]["error_code"] == "paper_review_worker_failed"
    assert published[0][0] == "session-1"
    assert published[0][1]["event"] == "run_failed"
    assert published[0][1]["message_id"] == "assistant-1"


def test_paper_review_worker_lost_signal_persists_failed_state(monkeypatch):
    from worker.tasks import paper_review_chat_task as task_mod

    persisted: list[tuple[dict, str, str]] = []

    def fake_persist(payload, exc, *, error_code="paper_review_worker_failed"):
        persisted.append((payload, str(exc), error_code))

    monkeypatch.setattr(task_mod, "_persist_paper_review_failure", fake_persist)
    monkeypatch.setattr(task_mod, "run_celery_async", lambda awaitable: None)

    class WorkerLostError(Exception):
        pass

    task_mod._persist_paper_review_worker_lost(
        sender=SimpleNamespace(name="worker.tasks.paper_review_chat_task.run_paper_review_chat_workflow"),
        task_id="workflow-1",
        exception=WorkerLostError("Worker exited prematurely: signal 9 (SIGKILL)"),
        args=(
            {
                "org_id": "org-1",
                "session_id": "session-1",
                "assistant_message_id": "assistant-1",
                "workflow_run_id": "workflow-1",
            },
        ),
    )

    assert persisted == [
        (
            {
                "org_id": "org-1",
                "session_id": "session-1",
                "assistant_message_id": "assistant-1",
                "workflow_run_id": "workflow-1",
            },
            "Worker exited prematurely: signal 9 (SIGKILL)",
            "paper_review_worker_lost",
        )
    ]
