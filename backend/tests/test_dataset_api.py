from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from app.api.v1 import datasets as dataset_api
from app.schemas.dataset import (
    DatasetCreateRequest,
    DatasetDetailResponse,
    DatasetSampleCreateRequest,
    DatasetSampleResponse,
    DatasetUpdateRequest,
)
from app.schemas.user import CurrentUser


@dataclass
class FakeAsyncSession:
    commit_calls: int = 0

    async def commit(self) -> None:
        self.commit_calls += 1


def build_current_user() -> CurrentUser:
    return CurrentUser(
        user_id="user-1",
        org_id="org-1",
        role="algorithm_engineer",
        roles=["algorithm_engineer"],
        plan_tier="team",
        capabilities=["dataset"],
        workspaces=["algorithm"],
        default_workspace="algorithm",
    )


def build_dataset_detail() -> DatasetDetailResponse:
    now = datetime(2026, 5, 21, 10, 0, 0)
    return DatasetDetailResponse(
        id="ds-1",
        org_id="org-1",
        created_by="user-1",
        name="demo dataset",
        description="demo",
        modality="image",
        tags=["smoke"],
        status="active",
        sample_count=0,
        image_sample_count=0,
        video_sample_count=0,
        text_sample_count=0,
        uploaded_bytes=0,
        knowledge_graph_status="idle",
        alignment_status="idle",
        augmentation_status="idle",
        created_at=now,
        updated_at=now,
        recent_jobs=[],
    )


def build_sample_response() -> DatasetSampleResponse:
    now = datetime(2026, 5, 21, 10, 5, 0)
    return DatasetSampleResponse(
        id="sample-1",
        org_id="org-1",
        dataset_id="ds-1",
        created_by="user-1",
        sample_type="image",
        sample_name="demo.png",
        text_content=None,
        content_type="image/png",
        size_bytes=3,
        checksum_sha256="abc",
        storage_backend="local",
        bucket="dataset-assets",
        object_key="datasets/org-1/ds-1/demo.png",
        file_url="/uploads/datasets/org-1/ds-1/demo.png",
        annotation_data=None,
        quality_score=None,
        related_entities=None,
        source_metadata={"original_filename": "demo.png"},
        preview_text="demo.png",
        created_at=now,
        updated_at=now,
    )


class FakeDatasetService:
    def __init__(self, *_args, **_kwargs):
        self.detail = build_dataset_detail()
        self.sample = build_sample_response()

    async def create_dataset(self, payload: DatasetCreateRequest) -> DatasetDetailResponse:
        assert payload.name == "demo dataset"
        return self.detail

    async def list_dataset_name_options(self, *, keyword: str | None = None, modality: str | None = None, status: str | None = None, limit: int = 100):
        assert modality == "image"
        assert status == "active"
        assert limit == 50
        return [{"name": "demo dataset"}, {"name": "candidate set"}]

    async def update_dataset(self, dataset_id: str, payload: DatasetUpdateRequest) -> DatasetDetailResponse:
        assert dataset_id == "ds-1"
        assert payload.name == "renamed"
        return self.detail

    async def delete_dataset(self, dataset_id: str) -> None:
        assert dataset_id == "ds-1"

    async def create_text_sample(self, *, dataset_id: str, payload: DatasetSampleCreateRequest) -> DatasetSampleResponse:
        assert dataset_id == "ds-1"
        assert payload.text_content == "hello"
        sample = self.sample.model_copy(update={"sample_type": "text", "text_content": "hello", "preview_text": "hello"})
        return sample

    async def upload_image_samples(self, *, dataset_id: str, files: list[object]) -> list[DatasetSampleResponse]:
        assert dataset_id == "ds-1"
        assert len(files) == 1
        return [self.sample]

    async def delete_sample(self, *, dataset_id: str, sample_id: str) -> None:
        assert dataset_id == "ds-1"
        assert sample_id == "sample-1"


@pytest.fixture
def fake_service(monkeypatch):
    monkeypatch.setattr(dataset_api, "DatasetService", FakeDatasetService)


@pytest.mark.asyncio
async def test_create_dataset_commits_before_return(fake_service):
    session = FakeAsyncSession()

    response = await dataset_api.create_dataset(
        payload=DatasetCreateRequest(name="demo dataset", modality="image"),
        current=build_current_user(),
        db=session,
    )

    assert response.data is not None
    assert response.data.id == "ds-1"
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_list_dataset_names_returns_name_only_options(fake_service):
    session = FakeAsyncSession()

    response = await dataset_api.list_dataset_names(
        keyword="demo",
        modality="image",
        status_text="active",
        limit=50,
        current=build_current_user(),
        db=session,
    )

    assert response.data == [{"name": "demo dataset"}, {"name": "candidate set"}]
    assert session.commit_calls == 0


@pytest.mark.asyncio
async def test_update_dataset_commits_before_return(fake_service):
    session = FakeAsyncSession()

    response = await dataset_api.update_dataset(
        dataset_id="ds-1",
        payload=DatasetUpdateRequest(name="renamed"),
        current=build_current_user(),
        db=session,
    )

    assert response.data is not None
    assert response.data.id == "ds-1"
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_delete_dataset_commits_before_return(fake_service):
    session = FakeAsyncSession()

    response = await dataset_api.delete_dataset(
        dataset_id="ds-1",
        current=build_current_user(),
        db=session,
    )

    assert response.data == {"deleted": True}
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_create_text_sample_commits_before_return(fake_service):
    session = FakeAsyncSession()

    response = await dataset_api.create_text_sample(
        dataset_id="ds-1",
        payload=DatasetSampleCreateRequest(text_content="hello"),
        current=build_current_user(),
        db=session,
    )

    assert response.data is not None
    assert response.data.sample_type == "text"
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_upload_image_samples_commits_before_return(fake_service):
    session = FakeAsyncSession()

    response = await dataset_api.upload_image_samples(
        dataset_id="ds-1",
        files=[object()],
        current=build_current_user(),
        db=session,
    )

    assert response.data is not None
    assert len(response.data) == 1
    assert response.data[0].sample_type == "image"
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_delete_dataset_sample_commits_before_return(fake_service):
    session = FakeAsyncSession()

    response = await dataset_api.delete_dataset_sample(
        dataset_id="ds-1",
        sample_id="sample-1",
        current=build_current_user(),
        db=session,
    )

    assert response.data == {"deleted": True}
    assert session.commit_calls == 1
