import pytest

from app.api.v1 import agent as agent_api
from app.schemas.user import CurrentUser
from types import SimpleNamespace


class FakeTaskRepository:
    def __init__(self, db):
        self._db = db

    async def get(self, org_id: str, task_id: str):
        return SimpleNamespace(id=task_id, org_id=org_id)

    async def get_for_user(self, org_id: str, task_id: str, owner_user_id: str | None = None):
        return SimpleNamespace(id=task_id, org_id=org_id, created_by=owner_user_id)


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
async def test_run_task_pipeline_delegates_to_shared_launcher(monkeypatch):
    monkeypatch.setattr(agent_api, "TaskRepository", FakeTaskRepository)
    async def fake_launch(*, task_id: str, org_id: str):
        assert task_id == "task-1"
        assert org_id == "org-1"
        return {"mode": "local_background", "job_id": None}
    monkeypatch.setattr(agent_api, "launch_task_execution", fake_launch)

    result = await agent_api.run_task_pipeline("task-1", current=build_current_user(), db=object())

    assert result.data == {"mode": "local_background", "job_id": None}
