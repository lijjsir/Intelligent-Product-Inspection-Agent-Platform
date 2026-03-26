from datetime import datetime

import pytest

from app.core.exceptions import ValidationError
from app.schemas.task import TaskResponse
from app.services.task_service import TaskService


class FakeTask:
    def __init__(self):
        self.id = "task-1"
        self.org_id = "org-1"
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

    async def create(self, task):
        fake = FakeTask()
        fake.created_by = task.created_by
        fake.meta_data = task.meta_data
        fake.spec_code = task.spec_code
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
