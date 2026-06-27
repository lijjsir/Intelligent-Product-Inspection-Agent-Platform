from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.api.v1 import tasks as task_api
from app.core.permissions import require_role
from app.schemas.task import TaskResultIngestRequest, TaskResultIngestResponse
from app.schemas.user import CurrentUser

TASK_ID = "019e5e1b-f06e-75b6-b59b-5c8905e88d8b"
RAG_SPACE_ID = "019e5e1b-f06e-75b6-b59b-5c8905e88d81"
DATASET_ID = "019e5e1b-f06e-75b6-b59b-5c8905e88d82"


@dataclass
class FakeAsyncSession:
    commit_calls: int = 0

    async def commit(self) -> None:
        self.commit_calls += 1


@dataclass
class FakeTaskCreateSession:
    commit_calls: int = 0

    async def commit(self) -> None:
        self.commit_calls += 1


def build_current_user(role: str = "algorithm_engineer") -> CurrentUser:
    return CurrentUser(
        user_id="algo-1",
        org_id="org-1",
        role=role,
        roles=[role],
        plan_tier="team",
        capabilities=["task", "dataset"],
        workspaces=["algorithm"],
        default_workspace="algorithm",
    )


class FakeTaskResultIngestService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def ingest_task_result(self, *, task_id: str, payload: TaskResultIngestRequest) -> TaskResultIngestResponse:
        assert task_id == TASK_ID
        assert payload.target == "both"
        return TaskResultIngestResponse(
            task_id=task_id,
            target=payload.target,
            mode=payload.mode,
            rag_space_id=payload.rag_space_id,
            dataset_id=payload.dataset_id,
            dataset_name=payload.dataset_name,
            created_document_count=1,
            created_sample_count=2,
            skipped_count=0,
            warnings=[],
        )


class FakeTaskService:
    def __init__(self, db, org_id, actor_user_id=None, actor_role=None):
        self._db = db
        self._org_id = org_id
        self._actor_user_id = actor_user_id
        self._actor_role = actor_role

    async def create_task(
        self,
        *,
        created_by: str,
        product_id: str,
        spec_code: str,
        product_sku_id: str | None = None,
        batch_id: str | None = None,
        inspection_standard_id: str | None = None,
        image_urls: list[str],
        image_items=None,
        priority: int,
        metadata=None,
    ):
        return SimpleNamespace(
            id="task-1",
            org_id=self._org_id,
            product_id=product_id,
            spec_code=spec_code,
            product_sku_id=product_sku_id,
            batch_id=batch_id,
            inspection_standard_id=inspection_standard_id,
            status="pending",
            priority=priority,
            image_urls=image_urls,
            image_items=image_items,
            meta_data=metadata,
        )

    async def get_task(self, task_id: str):
        return SimpleNamespace(
            id=task_id,
            org_id=self._org_id,
            product_id="P-1",
            spec_code="STD-1",
            product_sku_id="sku-1",
            batch_id="batch-1",
            inspection_standard_id="standard-1",
            product_line_name="产品线 1",
            product_name="产品 1",
            batch_no="B-1",
            standard_name="检测标准 1",
            status="queued",
            priority=5,
            image_urls=["https://example.com/a.png"],
            image_items=None,
            execution={"mode": "local_background"},
            has_result=False,
            has_stability=False,
            result_id=None,
            stability_id=None,
            source_kind=None,
            source_graph=None,
            org_slug=None,
            created_at=None,
            updated_at=None,
        )


@pytest.fixture
def fake_service(monkeypatch):
    monkeypatch.setattr(task_api, "TaskResultIngestService", FakeTaskResultIngestService)


@pytest.mark.asyncio
async def test_ingest_task_result_returns_response(fake_service):
    response = await task_api.ingest_task_result(
        task_id=TASK_ID,
        payload=TaskResultIngestRequest(
            target="both",
            rag_space_id=RAG_SPACE_ID,
            dataset_name="候选训练集-A",
            mode="candidate",
        ),
        current=build_current_user(),
        db=FakeAsyncSession(),
    )

    assert response.data is not None
    assert response.data.created_document_count == 1
    assert response.data.created_sample_count == 2


@pytest.mark.asyncio
async def test_ingest_task_result_allows_expert_role_for_rag_only(fake_service):
    response = await task_api.ingest_task_result(
        task_id=TASK_ID,
        payload=TaskResultIngestRequest(
            target="both",
            rag_space_id=RAG_SPACE_ID,
            dataset_name="候选训练集-A",
            mode="candidate",
        ),
        current=build_current_user(role="expert"),
        db=FakeAsyncSession(),
    )

    assert response.data is not None
    assert response.data.task_id == TASK_ID


def test_ingest_request_rejects_non_uuid_dataset_id():
    with pytest.raises(PydanticValidationError, match="dataset_id must be a valid UUID"):
        TaskResultIngestRequest(
            target="dataset",
            dataset_id="test",
            mode="candidate",
        )


def test_ingest_request_accepts_dataset_name_without_uuid():
    payload = TaskResultIngestRequest(
        target="dataset",
        dataset_name="候选训练集-A",
        mode="candidate",
    )

    assert payload.dataset_name == "候选训练集-A"


def test_task_permission_allows_algorithm_engineer_read_access():
    require_role("task", "algorithm_engineer")


@pytest.mark.asyncio
async def test_create_task_triggers_launch_and_returns_refreshed_task(monkeypatch):
    launched: list[dict] = []

    async def fake_launch(*, task_id: str, org_id: str):
        launched.append({"task_id": task_id, "org_id": org_id})
        return {"mode": "local_background", "job_id": None, "status": "queued"}

    monkeypatch.setattr(task_api, "TaskService", FakeTaskService)
    monkeypatch.setattr(task_api, "launch_task_execution", fake_launch)

    payload = task_api.TaskCreate(
        product_sku_id="sku-1",
        batch_id="batch-1",
        inspection_standard_id="standard-1",
        product_id="P-1",
        spec_code="STD-1",
        image_urls=["https://example.com/a.png"],
        priority=5,
        metadata={"source": "task_list"},
    )

    db = FakeTaskCreateSession()

    result = await task_api.create_task(payload, current=build_current_user(), db=db)

    assert launched == [{"task_id": "task-1", "org_id": "org-1"}]
    assert db.commit_calls == 1
    assert result.data.id == "task-1"
    assert result.data.status == "queued"
    assert result.data.execution == {"mode": "local_background"}
