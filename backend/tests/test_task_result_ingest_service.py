from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.schemas.task import TaskResultIngestRequest
from app.services.task_result_ingest_service import TaskResultIngestService

TASK_ID = "019e5e1b-f06e-75b6-b59b-5c8905e88d8b"
RAG_SPACE_ID = "019e5e1b-f06e-75b6-b59b-5c8905e88d81"
DATASET_ID = "019e5e1b-f06e-75b6-b59b-5c8905e88d82"


@dataclass
class FakeSession:
    refreshed: list[str] | None = None


class FakeTaskRepo:
    def __init__(self, _session):
        self.task = SimpleNamespace(
            id=TASK_ID,
            org_id="org-1",
            created_by="expert-1",
            product_id="product-1",
            spec_code="STD-1",
            status="done",
            image_urls=["https://example.com/a.png", "https://example.com/b.png"],
            image_items=[
                {"index": 0, "url": "https://example.com/a.png", "hash": "hash-a", "sample_number": 1},
                {"index": 1, "url": "https://example.com/b.png", "hash": "hash-b", "sample_number": 2},
            ],
            created_at=datetime(2026, 5, 25, 10, 0, 0),
        )

    async def get_for_user(self, org_id, task_id, owner_user_id=None):
        assert task_id == TASK_ID
        assert org_id == "org-1"
        assert owner_user_id is None
        return self.task


class FakeResultRepo:
    def __init__(self, _session):
        self.result = SimpleNamespace(
            id="result-1",
            verdict="fail",
            overall_score=0.82,
            defects=[
                {
                    "type": "scratch",
                    "confidence": 0.95,
                    "bbox": [0.1, 0.2, 0.3, 0.4],
                    "description": "front scratch",
                    "image_index": 1,
                },
                {
                    "type": "dent",
                    "confidence": 0.77,
                    "bbox": [0.4, 0.3, 0.2, 0.1],
                    "description": "missing image index",
                },
            ],
            citations={
                "items": [
                    {"source": "qa-spec.pdf", "quote": "标准要求表面不得有划痕。"},
                ]
            },
            reasoning_chain={"secret": "should-not-appear"},
        )

    async def get_by_task(self, org_id: str, task_id: str):
        assert org_id == "org-1"
        assert task_id == TASK_ID
        return self.result


class FakeStabilityRepo:
    def __init__(self, _session):
        self.row = SimpleNamespace(
            id="st-1",
            risk_level="high",
            evidence_score=0.88,
            traceability_score=0.79,
        )

    async def get_by_task(self, org_id: str, task_id: str):
        assert org_id == "org-1"
        assert task_id == TASK_ID
        return self.row


class FakeDatasetRepo:
    def __init__(self, _session):
        self.dataset = SimpleNamespace(
            id=DATASET_ID,
            org_id="org-1",
            created_by="algo-1",
            name="缺陷样本集",
            status="active",
            modality="image+text",
        )
        self.recalculate_calls: list[str] = []

    async def get(self, *, org_id: str, dataset_id: str, owner_user_id: str):
        assert org_id == "org-1"
        assert dataset_id == DATASET_ID
        assert owner_user_id == "algo-1"
        return self.dataset

    async def recalculate_counters(self, *, dataset_id: str):
        self.recalculate_calls.append(dataset_id)
        return self.dataset

    async def get_by_name(self, *, org_id: str, owner_user_id: str, name: str, exclude_dataset_id: str | None = None):
        assert org_id == "org-1"
        assert owner_user_id == "algo-1"
        if name == self.dataset.name:
            return self.dataset
        return None


class FakeDatasetSampleRepo:
    def __init__(self, _session):
        self.samples: list[SimpleNamespace] = []

    async def list_for_dataset_all(self, *, org_id: str, dataset_id: str, owner_user_id: str):
        assert org_id == "org-1"
        assert dataset_id == DATASET_ID
        assert owner_user_id == "algo-1"
        return list(self.samples)

    async def create(self, payload: dict):
        row = SimpleNamespace(**payload)
        self.samples.append(row)
        return row


class FakeDatasetJobRepo:
    def __init__(self, _session):
        self.jobs: list[dict] = []

    async def create(self, payload: dict):
        self.jobs.append(payload)
        return SimpleNamespace(**payload)


class FakeRagSpaceService:
    existing_docs: list[SimpleNamespace] = []
    created_docs: list[dict] = []

    def __init__(self, *_args, **_kwargs):
        pass

    async def list_documents(self, *, rag_space_id: str, limit: int = 1000):
        assert rag_space_id == RAG_SPACE_ID
        assert limit == 5000
        return list(self.existing_docs)

    async def create_generated_document(self, *, rag_space_id: str, file_name: str, content: bytes, content_type: str | None = None, parent_node_id: str | None = None):
        assert rag_space_id == RAG_SPACE_ID
        self.created_docs.append(
            {
                "file_name": file_name,
                "content": content.decode("utf-8"),
                "content_type": content_type,
                "parent_node_id": parent_node_id,
            }
        )
        row = SimpleNamespace(file_name=file_name)
        self.existing_docs.append(row)
        return SimpleNamespace(id="node-1")


class FakeObjectStorage:
    backend_name = "local"

    def __init__(self):
        self.put_calls: list[dict] = []
        self.deleted: list[tuple[str, str]] = []
        self.buckets: list[str] = []

    def ensure_bucket(self, bucket: str) -> None:
        self.buckets.append(bucket)

    def put_bytes(self, *, bucket: str, object_key: str, data: bytes, content_type: str | None = None) -> dict:
        self.put_calls.append(
            {
                "bucket": bucket,
                "object_key": object_key,
                "data": data,
                "content_type": content_type,
            }
        )
        return {
            "bucket": bucket,
            "object_key": object_key,
            "url": f"/uploads/{object_key}",
            "content_type": content_type,
            "size_bytes": len(data),
        }

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))


@pytest.fixture
def fake_ingest_deps(monkeypatch):
    dataset_repo = FakeDatasetRepo(None)
    sample_repo = FakeDatasetSampleRepo(None)
    job_repo = FakeDatasetJobRepo(None)
    task_repo = FakeTaskRepo(None)
    result_repo = FakeResultRepo(None)
    stability_repo = FakeStabilityRepo(None)
    FakeRagSpaceService.existing_docs = []
    FakeRagSpaceService.created_docs = []
    fake_storage = FakeObjectStorage()

    monkeypatch.setattr("app.services.task_result_ingest_service.TaskRepository", lambda session: task_repo)
    monkeypatch.setattr("app.services.task_result_ingest_service.ResultRepository", lambda session: result_repo)
    monkeypatch.setattr("app.services.task_result_ingest_service.StabilityRepository", lambda session: stability_repo)
    monkeypatch.setattr("app.services.task_result_ingest_service.DatasetRepository", lambda session: dataset_repo)
    monkeypatch.setattr("app.services.task_result_ingest_service.DatasetSampleRepository", lambda session: sample_repo)
    monkeypatch.setattr("app.services.task_result_ingest_service.DatasetAsyncJobRepository", lambda session: job_repo)
    monkeypatch.setattr("app.services.task_result_ingest_service.RagSpaceService", FakeRagSpaceService)
    monkeypatch.setattr("app.services.task_result_ingest_service.build_object_storage", lambda: fake_storage)

    return {
        "dataset_repo": dataset_repo,
        "sample_repo": sample_repo,
        "job_repo": job_repo,
        "task_repo": task_repo,
        "result_repo": result_repo,
        "stability_repo": stability_repo,
        "storage": fake_storage,
    }


@pytest.mark.asyncio
async def test_ingest_task_result_imports_rag_and_dataset_candidates(fake_ingest_deps):
    service = TaskResultIngestService(
        session=FakeSession(),
        org_id="org-1",
        actor_user_id="algo-1",
        actor_role="algorithm_engineer",
    )

    result = await service.ingest_task_result(
        task_id=TASK_ID,
        payload=TaskResultIngestRequest(
            target="both",
            rag_space_id=RAG_SPACE_ID,
            dataset_name="缺陷样本集",
            mode="candidate",
        ),
    )

    assert result.created_document_count == 1
    assert result.created_sample_count == 2
    assert result.skipped_count == 0
    assert result.dataset_id == DATASET_ID
    assert result.dataset_name == "缺陷样本集"
    assert "missing image_index" not in FakeRagSpaceService.created_docs[0]["content"]
    assert "reasoning_chain" not in FakeRagSpaceService.created_docs[0]["content"]
    assert "should-not-appear" not in FakeRagSpaceService.created_docs[0]["content"]
    assert fake_ingest_deps["dataset_repo"].recalculate_calls == [DATASET_ID]
    assert len(fake_ingest_deps["sample_repo"].samples) == 2
    first_sample = fake_ingest_deps["sample_repo"].samples[0]
    second_sample = fake_ingest_deps["sample_repo"].samples[1]
    assert first_sample.source_metadata["review_status"] == "pending_review"
    assert second_sample.annotation_data["defects"][0]["type"] == "scratch"
    assert any("missing image_index" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_ingest_task_result_is_idempotent_for_existing_doc_and_samples(fake_ingest_deps):
    service = TaskResultIngestService(
        session=FakeSession(),
        org_id="org-1",
        actor_user_id="algo-1",
        actor_role="algorithm_engineer",
    )
    payload = TaskResultIngestRequest(
        target="both",
        rag_space_id=RAG_SPACE_ID,
        dataset_name="缺陷样本集",
        mode="candidate",
    )

    first = await service.ingest_task_result(task_id=TASK_ID, payload=payload)
    second = await service.ingest_task_result(task_id=TASK_ID, payload=payload)

    assert first.created_document_count == 1
    assert first.created_sample_count == 2
    assert second.created_document_count == 0
    assert second.created_sample_count == 0
    assert second.skipped_count == 3


@pytest.mark.asyncio
async def test_ingest_task_result_rejects_missing_result(fake_ingest_deps, monkeypatch):
    class EmptyResultRepo:
        def __init__(self, _session):
            pass

        async def get_by_task(self, org_id: str, task_id: str):
            return None

    monkeypatch.setattr("app.services.task_result_ingest_service.ResultRepository", EmptyResultRepo)
    service = TaskResultIngestService(
        session=FakeSession(),
        org_id="org-1",
        actor_user_id="algo-1",
        actor_role="algorithm_engineer",
    )

    with pytest.raises(ValidationError, match="task result not found"):
        await service.ingest_task_result(
            task_id=TASK_ID,
            payload=TaskResultIngestRequest(target="dataset", dataset_name="缺陷样本集", mode="candidate"),
        )


@pytest.mark.asyncio
async def test_ingest_task_result_warns_when_task_has_no_images(fake_ingest_deps):
    fake_ingest_deps["task_repo"].task.image_urls = []
    fake_ingest_deps["task_repo"].task.image_items = []
    service = TaskResultIngestService(
        session=FakeSession(),
        org_id="org-1",
        actor_user_id="algo-1",
        actor_role="algorithm_engineer",
    )

    result = await service.ingest_task_result(
        task_id=TASK_ID,
        payload=TaskResultIngestRequest(target="dataset", dataset_name="缺陷样本集", mode="candidate"),
    )

    assert result.created_sample_count == 0
    assert result.skipped_count == 0
    assert result.warnings == ["task has no image evidence to import into dataset candidates"]


@pytest.mark.asyncio
async def test_ingest_task_result_rejects_invalid_task_id(fake_ingest_deps):
    service = TaskResultIngestService(
        session=FakeSession(),
        org_id="org-1",
        actor_user_id="algo-1",
        actor_role="algorithm_engineer",
    )

    payload = TaskResultIngestRequest(target="dataset", dataset_name="缺陷样本集", mode="candidate")

    with pytest.raises(ValidationError, match="task_id must be a valid UUID"):
        await service.ingest_task_result(
            task_id="test",
            payload=payload,
        )


@pytest.mark.asyncio
async def test_ingest_task_result_rejects_missing_dataset_name(fake_ingest_deps):
    service = TaskResultIngestService(
        session=FakeSession(),
        org_id="org-1",
        actor_user_id="algo-1",
        actor_role="algorithm_engineer",
    )

    with pytest.raises(ValidationError, match="dataset_name is required when target includes dataset"):
        await service.ingest_task_result(
            task_id=TASK_ID,
            payload=TaskResultIngestRequest(target="dataset", mode="candidate"),
        )


@pytest.mark.asyncio
async def test_ingest_task_result_persists_data_url_images_to_object_storage(fake_ingest_deps):
    fake_ingest_deps["task_repo"].task.image_urls = ["data:image/jpeg;base64,aGVsbG8="]
    fake_ingest_deps["task_repo"].task.image_items = [
        {"index": 0, "url": "data:image/jpeg;base64,aGVsbG8=", "hash": "hash-data-url", "sample_number": 1},
    ]
    service = TaskResultIngestService(
        session=FakeSession(),
        org_id="org-1",
        actor_user_id="algo-1",
        actor_role="algorithm_engineer",
    )

    result = await service.ingest_task_result(
        task_id=TASK_ID,
        payload=TaskResultIngestRequest(target="dataset", dataset_name="缺陷样本集", mode="candidate"),
    )

    assert result.created_sample_count == 1
    assert len(fake_ingest_deps["storage"].put_calls) == 1
    sample = fake_ingest_deps["sample_repo"].samples[0]
    assert sample.storage_backend == "local"
    assert sample.file_url.startswith("/uploads/datasets/")
    assert not sample.file_url.startswith("data:")
    assert sample.size_bytes == len(b"hello")
    assert sample.content_type == "image/jpeg"
