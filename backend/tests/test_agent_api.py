from types import SimpleNamespace

import pytest

from app.api.v1 import agent as agent_api
from app.schemas.user import CurrentUser


class FakeTaskRepository:
    def __init__(self, db):
        self._db = db

    async def get(self, org_id: str, task_id: str):
        return SimpleNamespace(id=task_id, org_id=org_id)


def build_current_user() -> CurrentUser:
    return CurrentUser(
        user_id="user-1",
        org_id="org-1",
        role="admin",
        roles=["admin"],
        plan_tier="basic",
        capabilities=[],
        workspaces=["app"],
        default_workspace="app",
    )


@pytest.mark.asyncio
async def test_run_task_pipeline_falls_back_to_local_background_when_worker_missing(monkeypatch):
    scheduled = []
    delay_called = {"value": False}

    async def fake_has_no_worker():
        return False

    async def fake_pipeline(*, task_id: str, org_id: str):
        return {"task_id": task_id, "org_id": org_id}

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return SimpleNamespace()

    def fake_delay(payload: dict):
        delay_called["value"] = True
        return SimpleNamespace(id="job-1")

    monkeypatch.setattr(agent_api, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_api, "_has_active_celery_worker", fake_has_no_worker)
    monkeypatch.setattr(agent_api, "run_inspection_pipeline", fake_pipeline)
    monkeypatch.setattr(agent_api.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(agent_api.run_inspection, "delay", fake_delay)

    result = await agent_api.run_task_pipeline("task-1", current=build_current_user(), db=object())

    assert result.data == {"mode": "local_background", "job_id": None}
    assert delay_called["value"] is False
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_run_task_pipeline_uses_celery_when_worker_is_available(monkeypatch):
    created_tasks = []

    async def fake_has_worker():
        return True

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return SimpleNamespace()

    def fake_delay(payload: dict):
        assert payload == {"task_id": "task-1", "org_id": "org-1"}
        return SimpleNamespace(id="job-1")

    monkeypatch.setattr(agent_api, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_api, "_has_active_celery_worker", fake_has_worker)
    monkeypatch.setattr(agent_api.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(agent_api.run_inspection, "delay", fake_delay)

    result = await agent_api.run_task_pipeline("task-1", current=build_current_user(), db=object())

    assert result.data == {"mode": "celery", "job_id": "job-1"}
    assert created_tasks == []
