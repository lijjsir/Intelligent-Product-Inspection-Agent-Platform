from datetime import datetime

import pytest

from app.core.exceptions import ValidationError
from app.schemas.task import TaskResponse
from app.services.task_service import TaskService


class FakeTask:
    def __init__(self):
        self.id = "task-1"
        self.org_id = "org-1"
        self.created_by = "user-1"
        self.product_id = "product-1"
        self.spec_code = "STD-1"
        self.status = "pending"
        self.priority = 5
        self.image_urls = ["https://example.com/a.png"]
        self.created_at = datetime(2026, 3, 25, 12, 0, 0)
        self.updated_at = datetime(2026, 3, 25, 12, 0, 1)


class FakeSession:
    def __init__(self):
        self.refreshed = []

    async def refresh(self, task):
        self.refreshed.append(task.id)


class FakeTaskRepo:
    def __init__(self, session):
        self._session = session
        self.get_calls = []
        self.list_calls = []
        self.deleted_calls = []

    async def create(self, task):
        fake = FakeTask()
        fake.created_by = task.created_by
        fake.meta_data = task.meta_data
        fake.spec_code = task.spec_code
        return fake

    async def get_for_user(self, org_id, task_id, owner_user_id=None):
        self.get_calls.append({"org_id": org_id, "task_id": task_id, "owner_user_id": owner_user_id})
        fake = FakeTask()
        fake.id = task_id
        return fake

    async def list_paged(self, org_id, filters, page, size, owner_user_id=None):
        self.list_calls.append(
            {
                "org_id": org_id,
                "filters": filters,
                "page": page,
                "size": size,
                "owner_user_id": owner_user_id,
            }
        )
        return [FakeTask()], 1

    async def soft_delete(self, org_id, task_id, owner_user_id=None):
        self.deleted_calls.append({"org_id": org_id, "task_id": task_id, "owner_user_id": owner_user_id})
        fake = FakeTask()
        fake.id = task_id
        return fake


class FakeSpecRepo:
    def __init__(self, session):
        self._session = session
        self.active_specs = {"STD-1": object()}

    async def get_active_spec(self, org_id: str, spec_code: str):
        return self.active_specs.get(spec_code)


class FakeAuditService:
    def __init__(self, session):
        self._session = session
        self.calls = []

    async def write_outbox(self, payload: dict):
        self.calls.append(payload)


class FakeQuery:
    def __init__(self):
        self.page = 1
        self.size = 20

    def to_filters(self):
        return {"status": "pending"}


@pytest.mark.asyncio
async def test_create_task_returns_serializable_task(monkeypatch):
    monkeypatch.setattr("app.services.task_service.TaskRepository", FakeTaskRepo)
    monkeypatch.setattr("app.services.task_service.AuditService", FakeAuditService)
    monkeypatch.setattr("app.services.task_service.InspectionSpecRepository", FakeSpecRepo)

    session = FakeSession()
    service = TaskService(session=session, org_id="org-1")
    task = await service.create_task(
        created_by="user-1",
        product_id="product-1",
        spec_code="STD-1",
        image_urls=["https://example.com/a.png"],
        priority=5,
        metadata={"batch": "B-1"},
    )

    response = TaskResponse.model_validate(task)

    assert response.id == "task-1"
    assert response.spec_code == "STD-1"
    assert response.created_at == datetime(2026, 3, 25, 12, 0, 0)
    assert response.updated_at == datetime(2026, 3, 25, 12, 0, 1)
    assert session.refreshed == ["task-1"]


@pytest.mark.asyncio
async def test_create_task_rejects_missing_active_spec(monkeypatch):
    monkeypatch.setattr("app.services.task_service.TaskRepository", FakeTaskRepo)
    monkeypatch.setattr("app.services.task_service.AuditService", FakeAuditService)
    monkeypatch.setattr("app.services.task_service.InspectionSpecRepository", FakeSpecRepo)

    session = FakeSession()
    service = TaskService(session=session, org_id="org-1")

    with pytest.raises(ValidationError, match="不存在或未启用"):
        await service.create_task(
            created_by="user-1",
            product_id="product-1",
            spec_code="STD-MISSING",
            image_urls=["https://example.com/a.png"],
            priority=5,
            metadata=None,
        )


@pytest.mark.asyncio
async def test_list_tasks_filters_by_owner_for_user_role(monkeypatch):
    repo = FakeTaskRepo(None)
    monkeypatch.setattr("app.services.task_service.TaskRepository", lambda session: repo)
    monkeypatch.setattr("app.services.task_service.AuditService", FakeAuditService)
    monkeypatch.setattr("app.services.task_service.InspectionSpecRepository", FakeSpecRepo)

    service = TaskService(session=FakeSession(), org_id="org-1", actor_user_id="user-1", actor_role="user")

    rows, total = await service.list_tasks(FakeQuery())

    assert total == 1
    assert rows[0].id == "task-1"
    assert repo.list_calls == [
        {
            "org_id": "org-1",
            "filters": {"status": "pending"},
            "page": 1,
            "size": 20,
            "owner_user_id": "user-1",
        }
    ]


@pytest.mark.asyncio
async def test_list_tasks_ignores_org_scope_for_admin_role(monkeypatch):
    repo = FakeTaskRepo(None)
    monkeypatch.setattr("app.services.task_service.TaskRepository", lambda session: repo)
    monkeypatch.setattr("app.services.task_service.AuditService", FakeAuditService)
    monkeypatch.setattr("app.services.task_service.InspectionSpecRepository", FakeSpecRepo)

    service = TaskService(session=FakeSession(), org_id="org-1", actor_user_id="admin-1", actor_role="admin")

    await service.list_tasks(FakeQuery())

    assert repo.list_calls[0]["org_id"] is None
    assert repo.list_calls[0]["owner_user_id"] is None


@pytest.mark.asyncio
async def test_get_task_ignores_org_scope_for_admin_role(monkeypatch):
    repo = FakeTaskRepo(None)
    monkeypatch.setattr("app.services.task_service.TaskRepository", lambda session: repo)
    monkeypatch.setattr("app.services.task_service.AuditService", FakeAuditService)
    monkeypatch.setattr("app.services.task_service.InspectionSpecRepository", FakeSpecRepo)

    service = TaskService(session=FakeSession(), org_id="org-1", actor_user_id="admin-1", actor_role="admin")

    task = await service.get_task("task-cross-org")

    assert task is not None
    assert repo.get_calls == [
        {
            "org_id": None,
            "task_id": "task-cross-org",
            "owner_user_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_delete_task_rejects_running_task(monkeypatch):
    repo = FakeTaskRepo(None)

    async def _get_for_user(org_id, task_id, owner_user_id=None):
        fake = FakeTask()
        fake.id = task_id
        fake.status = "running"
        return fake

    repo.get_for_user = _get_for_user
    monkeypatch.setattr("app.services.task_service.TaskRepository", lambda session: repo)
    monkeypatch.setattr("app.services.task_service.AuditService", FakeAuditService)
    monkeypatch.setattr("app.services.task_service.InspectionSpecRepository", FakeSpecRepo)

    service = TaskService(session=FakeSession(), org_id="org-1", actor_user_id="user-1", actor_role="user")

    with pytest.raises(ValidationError, match="不能删除"):
        await service.delete_task("task-running")
