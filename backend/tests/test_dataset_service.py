from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.services import dataset_service as dataset_mod


@dataclass
class FakeDataset:
    id: str
    org_id: str
    created_by: str | None
    name: str
    description: str | None = None
    modality: str = "image_text"
    tags: list[str] | None = None
    status: str = "active"
    sample_count: int = 0
    image_sample_count: int = 0
    text_sample_count: int = 0
    uploaded_bytes: int = 0
    knowledge_graph_status: str = "idle"
    alignment_status: str = "idle"
    augmentation_status: str = "idle"
    created_at: datetime = datetime(2026, 5, 20, 9, 0, 0)
    updated_at: datetime = datetime(2026, 5, 20, 9, 0, 0)
    deleted_at: datetime | None = None


@dataclass
class FakeSample:
    id: str
    org_id: str
    dataset_id: str
    created_by: str | None
    sample_type: str
    sample_name: str | None = None
    text_content: str | None = None
    content_type: str | None = None
    size_bytes: int = 0
    checksum_sha256: str = ""
    storage_backend: str | None = None
    bucket: str | None = None
    object_key: str | None = None
    file_url: str | None = None
    annotation_data: dict | list | None = None
    quality_score: float | None = None
    related_entities: list | None = None
    source_metadata: dict | None = None
    preview_text: str | None = None
    created_at: datetime = datetime(2026, 5, 20, 9, 10, 0)
    updated_at: datetime = datetime(2026, 5, 20, 9, 10, 0)
    deleted_at: datetime | None = None


@dataclass
class FakeJob:
    id: str
    org_id: str
    dataset_id: str
    created_by: str | None
    job_type: str
    status: str
    payload_json: dict | None = None
    result_summary: dict | None = None
    error_message: str | None = None
    created_at: datetime = datetime(2026, 5, 20, 9, 11, 0)
    updated_at: datetime = datetime(2026, 5, 20, 9, 11, 0)
    deleted_at: datetime | None = None


class FakeDatasetRepo:
    def __init__(self, _session):
        self.datasets: dict[str, FakeDataset] = {
            "ds-1": FakeDataset(id="ds-1", org_id="org-1", created_by="user-1", name="缺陷样本集"),
            "text-only": FakeDataset(id="text-only", org_id="org-1", created_by="user-1", name="文本集", modality="text"),
        }

    async def create(self, payload: dict):
        created = FakeDataset(**payload, id=f"ds-{len(self.datasets) + 1}")
        self.datasets[created.id] = created
        return created

    async def list_for_owner(self, **kwargs):
        rows = [row for row in self.datasets.values() if row.created_by == kwargs["owner_user_id"] and row.deleted_at is None]
        return rows, len(rows)

    async def get(self, *, org_id: str, dataset_id: str, owner_user_id: str):
        row = self.datasets.get(dataset_id)
        if row and row.org_id == org_id and row.created_by == owner_user_id and row.deleted_at is None:
          return row
        return None

    async def save(self, obj, payload: dict):
        for key, value in payload.items():
            setattr(obj, key, value)
        return obj

    async def soft_delete(self, obj):
        obj.deleted_at = datetime.utcnow()
        return obj

    async def recalculate_counters(self, *, dataset_id: str):
        return self.datasets.get(dataset_id)


class FakeSampleRepo:
    def __init__(self, _session):
        self.samples: list[FakeSample] = []
        self.deleted_many: list[str] = []

    async def create(self, payload: dict):
        sample = FakeSample(id=f"sample-{len(self.samples) + 1}", **payload)
        self.samples.append(sample)
        return sample

    async def list_for_dataset(self, *, org_id: str, dataset_id: str, owner_user_id: str, page: int, size: int, sample_type: str | None = None):
        rows = [
            row for row in self.samples
            if row.org_id == org_id and row.dataset_id == dataset_id and row.created_by == owner_user_id and row.deleted_at is None
        ]
        if sample_type:
            rows = [row for row in rows if row.sample_type == sample_type]
        return rows, len(rows)

    async def get(self, *, org_id: str, dataset_id: str, sample_id: str, owner_user_id: str):
        for row in self.samples:
            if row.id == sample_id and row.org_id == org_id and row.dataset_id == dataset_id and row.created_by == owner_user_id and row.deleted_at is None:
                return row
        return None

    async def list_for_dataset_all(self, *, org_id: str, dataset_id: str, owner_user_id: str):
        return [
            row for row in self.samples
            if row.org_id == org_id and row.dataset_id == dataset_id and row.created_by == owner_user_id and row.deleted_at is None
        ]

    async def soft_delete(self, obj):
        obj.deleted_at = datetime.utcnow()
        return obj

    async def soft_delete_many(self, *, dataset_id: str):
        self.deleted_many.append(dataset_id)
        for row in self.samples:
            if row.dataset_id == dataset_id:
                row.deleted_at = datetime.utcnow()


class FakeJobRepo:
    def __init__(self, _session):
        self.jobs: list[FakeJob] = []

    async def create(self, payload: dict):
        job = FakeJob(id=f"job-{len(self.jobs) + 1}", **payload)
        self.jobs.append(job)
        return job

    async def list_recent_for_dataset(self, *, org_id: str, dataset_id: str, owner_user_id: str, limit: int = 10):
        return [job for job in self.jobs if job.org_id == org_id and job.dataset_id == dataset_id and job.created_by == owner_user_id][:limit]


class FakeObjectStorage:
    backend_name = "local"

    def __init__(self):
        self.deleted: list[tuple[str, str]] = []
        self.put_calls: list[dict] = []

    def ensure_bucket(self, bucket: str) -> None:
        return None

    def put_bytes(self, **kwargs):
        self.put_calls.append(kwargs)
        return {
            "bucket": kwargs["bucket"],
            "object_key": kwargs["object_key"],
            "url": f"/uploads/{kwargs['object_key']}",
            "content_type": kwargs.get("content_type") or "image/png",
            "size_bytes": len(kwargs["data"]),
        }

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))


class FakeUploadFile:
    def __init__(self, filename: str, content: bytes, content_type: str = "image/png"):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self):
        return self._content


@pytest.fixture
def service(monkeypatch):
    dataset_repo = FakeDatasetRepo(None)
    sample_repo = FakeSampleRepo(None)
    job_repo = FakeJobRepo(None)
    storage = FakeObjectStorage()

    monkeypatch.setattr(dataset_mod, "DatasetRepository", lambda session: dataset_repo)
    monkeypatch.setattr(dataset_mod, "DatasetSampleRepository", lambda session: sample_repo)
    monkeypatch.setattr(dataset_mod, "DatasetAsyncJobRepository", lambda session: job_repo)
    monkeypatch.setattr(dataset_mod, "build_object_storage", lambda: storage)

    svc = dataset_mod.DatasetService(None, "org-1", "user-1")
    return svc, dataset_repo, sample_repo, job_repo, storage


@pytest.mark.asyncio
async def test_create_text_sample_updates_jobs_and_returns_payload(service):
    svc, _dataset_repo, sample_repo, job_repo, _storage = service

    created = await svc.create_text_sample(
        dataset_id="ds-1",
        payload=dataset_mod.DatasetSampleCreateRequest(
            sample_name="case-1",
            text_content="显示屏表面存在细微划痕",
            annotation_data={"labels": ["scratch"]},
        ),
    )

    assert created.sample_type == "text"
    assert created.preview_text == "显示屏表面存在细微划痕"
    assert sample_repo.samples[0].annotation_data == {"labels": ["scratch"]}
    assert job_repo.jobs[-1].job_type == "text_sample_ingest"


@pytest.mark.asyncio
async def test_upload_image_samples_rejects_text_only_dataset(service):
    svc, _dataset_repo, _sample_repo, _job_repo, _storage = service

    with pytest.raises(ValidationError):
        await svc.upload_image_samples(
            dataset_id="text-only",
            files=[FakeUploadFile("demo.png", b"abc")],
        )


@pytest.mark.asyncio
async def test_delete_dataset_removes_objects_for_image_samples(service):
    svc, _dataset_repo, sample_repo, _job_repo, storage = service
    sample_repo.samples.append(
        FakeSample(
            id="sample-image",
            org_id="org-1",
            dataset_id="ds-1",
            created_by="user-1",
            sample_type="image",
            sample_name="demo.png",
            bucket="dataset-assets",
            object_key="datasets/org-1/ds-1/demo.png",
            file_url="/uploads/datasets/org-1/ds-1/demo.png",
        )
    )

    await svc.delete_dataset("ds-1")

    assert storage.deleted == [("dataset-assets", "datasets/org-1/ds-1/demo.png")]
    assert sample_repo.deleted_many == ["ds-1"]


@pytest.mark.asyncio
async def test_get_dataset_raises_for_foreign_owner(service):
    svc, _dataset_repo, _sample_repo, _job_repo, _storage = service

    with pytest.raises(NotFoundError):
        await svc.get_dataset("missing")
