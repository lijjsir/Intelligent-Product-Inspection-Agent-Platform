from __future__ import annotations

from dataclasses import dataclass

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
