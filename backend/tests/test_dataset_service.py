from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import io
import zipfile

import pytest

from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError, ValidationError
from app.core.config import settings
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
    video_sample_count: int = 0
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
        keyword = str(kwargs.get("keyword") or "").strip()
        modality = kwargs.get("modality")
        status = kwargs.get("status")
        if keyword:
            rows = [row for row in rows if keyword in row.name or keyword in str(row.description or "")]
        if modality:
            rows = [row for row in rows if row.modality == modality]
        if status:
            rows = [row for row in rows if row.status == status]
        rows = rows[: int(kwargs.get("size") or len(rows))]
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
        obj.deleted_at = utcnow()
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
        obj.deleted_at = utcnow()
        return obj

    async def soft_delete_many(self, *, dataset_id: str):
        self.deleted_many.append(dataset_id)
        for row in self.samples:
            if row.dataset_id == dataset_id:
                row.deleted_at = utcnow()


class FakeJobRepo:
    def __init__(self, _session):
        self.jobs: list[FakeJob] = []

    async def create(self, payload: dict):
        job = FakeJob(id=f"job-{len(self.jobs) + 1}", **payload)
        self.jobs.append(job)
        return job

    async def list_recent_for_dataset(self, *, org_id: str, dataset_id: str, owner_user_id: str, limit: int = 10):
        return [job for job in self.jobs if job.org_id == org_id and job.dataset_id == dataset_id and job.created_by == owner_user_id][:limit]

    async def get(self, *, org_id: str, dataset_id: str, job_id: str, owner_user_id: str):
        for row in self.jobs:
            if row.id == job_id and row.org_id == org_id and row.dataset_id == dataset_id and row.created_by == owner_user_id:
                return row
        return None


@dataclass
class FakeUploadSession:
    id: str
    org_id: str
    dataset_id: str
    created_by: str | None
    file_name: str
    content_type: str | None
    file_size: int
    chunk_size: int
    total_chunks: int
    bucket: str | None
    object_key: str | None
    uploaded_parts_json: list | dict | None
    status: str = "pending"
    error_message: str | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = datetime(2026, 5, 20, 9, 11, 0)
    updated_at: datetime = datetime(2026, 5, 20, 9, 11, 0)
    deleted_at: datetime | None = None


class FakeUploadRepo:
    def __init__(self, _session):
        self.uploads: dict[str, FakeUploadSession] = {}

    async def create(self, payload: dict):
        row = FakeUploadSession(id=f"upload-{len(self.uploads) + 1}", **payload)
        self.uploads[row.id] = row
        return row

    async def get(self, *, org_id: str, dataset_id: str, session_id: str, owner_user_id: str):
        row = self.uploads.get(session_id)
        if row and row.org_id == org_id and row.dataset_id == dataset_id and row.created_by == owner_user_id:
            return row
        return None

    async def save(self, obj, payload: dict):
        for key, value in payload.items():
            setattr(obj, key, value)
        return obj

    async def list_parts(self, upload):
        return list(upload.uploaded_parts_json or [])


class FakeObjectStorage:
    backend_name = "local"

    def __init__(self):
        self.deleted: list[tuple[str, str]] = []
        self.put_calls: list[dict] = []
        self.objects: dict[tuple[str, str], tuple[bytes, str | None]] = {}

    def ensure_bucket(self, bucket: str) -> None:
        return None

    def put_bytes(self, **kwargs):
        self.put_calls.append(kwargs)
        self.objects[(kwargs["bucket"], kwargs["object_key"])] = (kwargs["data"], kwargs.get("content_type"))
        return {
            "bucket": kwargs["bucket"],
            "object_key": kwargs["object_key"],
            "url": f"/uploads/{kwargs['object_key']}",
            "content_type": kwargs.get("content_type") or "image/png",
            "size_bytes": len(kwargs["data"]),
        }

    def get_bytes(self, *, bucket: str, object_key: str):
        stored = self.objects.get((bucket, object_key))
        if stored is None:
            return None
        return stored

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))

    def presign_download_url(self, *, bucket: str, object_key: str, expires_seconds: int = 3600) -> str:
        return f"/download/{object_key}"


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
    upload_repo = FakeUploadRepo(None)
    storage = FakeObjectStorage()

    monkeypatch.setattr(dataset_mod, "DatasetRepository", lambda session: dataset_repo)
    monkeypatch.setattr(dataset_mod, "DatasetSampleRepository", lambda session: sample_repo)
    monkeypatch.setattr(dataset_mod, "DatasetAsyncJobRepository", lambda session: job_repo)
    monkeypatch.setattr(dataset_mod, "DatasetUploadSessionRepository", lambda session: upload_repo)
    monkeypatch.setattr(dataset_mod, "build_object_storage", lambda: storage)

    svc = dataset_mod.DatasetService(None, "org-1", "user-1")
    return svc, dataset_repo, sample_repo, job_repo, upload_repo, storage


@pytest.mark.asyncio
async def test_create_text_sample_updates_jobs_and_returns_payload(service):
    svc, _dataset_repo, sample_repo, job_repo, _upload_repo, _storage = service

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
    svc, _dataset_repo, _sample_repo, _job_repo, _upload_repo, _storage = service

    with pytest.raises(ValidationError):
        await svc.upload_image_samples(
            dataset_id="text-only",
            files=[FakeUploadFile("demo.png", b"abc")],
        )


@pytest.mark.asyncio
async def test_delete_dataset_removes_objects_for_image_samples(service):
    svc, _dataset_repo, sample_repo, _job_repo, _upload_repo, storage = service
    sample_repo.samples.append(
        FakeSample(
            id="sample-image",
            org_id="org-1",
            dataset_id="ds-1",
            created_by="user-1",
            sample_type="image",
            sample_name="demo.png",
            bucket=settings.dataset_storage_bucket,
            object_key="datasets/org-1/ds-1/demo.png",
            file_url="/uploads/datasets/org-1/ds-1/demo.png",
        )
    )

    await svc.delete_dataset("ds-1")

    assert storage.deleted == [(settings.dataset_storage_bucket, "datasets/org-1/ds-1/demo.png")]
    assert sample_repo.deleted_many == ["ds-1"]


@pytest.mark.asyncio
async def test_get_dataset_raises_for_foreign_owner(service):
    svc, _dataset_repo, _sample_repo, _job_repo, _upload_repo, _storage = service

    with pytest.raises(NotFoundError):
        await svc.get_dataset("missing")


@pytest.mark.asyncio
async def test_list_dataset_name_options_returns_name_only(service):
    svc, _dataset_repo, _sample_repo, _job_repo, _upload_repo, _storage = service

    result = await svc.list_dataset_name_options(modality="image", status="active", limit=20)

    assert [item.name for item in result] == ["缺陷样本集"]


@pytest.mark.asyncio
async def test_complete_upload_session_creates_import_job(service, monkeypatch):
    svc, _dataset_repo, _sample_repo, job_repo, upload_repo, storage = service

    monkeypatch.setattr(dataset_mod, "has_active_celery_worker", lambda: False)
    monkeypatch.setattr(dataset_mod.asyncio, "create_task", lambda coro: None)

    init = await svc.init_upload_session(
        dataset_id="ds-1",
        payload=dataset_mod.DatasetUploadInitRequest(
            file_name="dataset.zip",
            content_type="application/zip",
            file_size=128,
            chunk_size=128,
            total_chunks=1,
        ),
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("sample.png", b"fake-image")
    await svc.upload_part(dataset_id="ds-1", session_id=init.session_id, part_number=1, content=buffer.getvalue())
    completed = await svc.complete_upload_session(
        dataset_id="ds-1",
        payload=dataset_mod.DatasetUploadCompleteRequest(session_id=init.session_id, uploaded_parts=[1]),
    )

    assert completed.job.status == "queued"
    assert job_repo.jobs[-1].job_type == "data_import"
    assert upload_repo.uploads[init.session_id].status == "completed"
    assert storage.get_bytes(bucket=init.bucket, object_key=init.object_key) is not None


@pytest.mark.asyncio
async def test_run_data_import_attaches_same_name_sidecars(service, monkeypatch):
    svc, _dataset_repo, sample_repo, job_repo, upload_repo, storage = service

    upload = await upload_repo.create(
        {
            "org_id": "org-1",
            "dataset_id": "ds-1",
            "created_by": "user-1",
            "file_name": "bundle.zip",
            "content_type": "application/zip",
            "file_size": 512,
            "chunk_size": 512,
            "total_chunks": 1,
            "bucket": settings.dataset_storage_bucket,
            "object_key": "datasets/org-1/ds-1/uploads/bundle.zip",
            "uploaded_parts_json": [1],
            "status": "completed",
            "expires_at": utcnow(),
        }
    )
    job = await job_repo.create(
        {
            "org_id": "org-1",
            "dataset_id": "ds-1",
            "created_by": "user-1",
            "job_type": "data_import",
            "status": "queued",
            "payload_json": {"upload_session_id": upload.id},
            "result_summary": {"status": "queued", "warnings": []},
        }
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("sample-1.png", b"fake-image")
        archive.writestr("sample-1.txt", "细微划痕位于边框右上角")
        archive.writestr("sample-1.json", '{"labels":["scratch"],"bbox":[1,2,3,4]}')
        archive.writestr("orphan.txt", "should be skipped")
    storage.put_bytes(
        bucket=settings.dataset_storage_bucket,
        object_key="datasets/org-1/ds-1/uploads/bundle.zip",
        data=buffer.getvalue(),
        content_type="application/zip",
    )

    service_factory = lambda session, org_id, user_id: svc
    monkeypatch.setattr(dataset_mod, "DatasetService", service_factory)

    await dataset_mod.run_dataset_import_pipeline(
        dataset_id="ds-1",
        job_id=job.id,
        upload_session_id=upload.id,
        bucket=settings.dataset_storage_bucket,
        object_key="datasets/org-1/ds-1/uploads/bundle.zip",
        org_id="org-1",
        user_id="user-1",
    )

    assert len(sample_repo.samples) == 1
    sample = sample_repo.samples[0]
    assert sample.sample_type == "image"
    assert sample.text_content == "细微划痕位于边框右上角"
    assert sample.annotation_data == {"labels": ["scratch"], "bbox": [1, 2, 3, 4]}
    assert sample.source_metadata["sidecar_text_filename"] == "sample-1.txt"
    assert sample.source_metadata["sidecar_annotation_filename"] == "sample-1.json"
    assert job.status == "completed"
    assert job.result_summary["text_sidecar_attached"] == 1
    assert job.result_summary["annotation_sidecar_attached"] == 1
    assert job.result_summary["skipped_files"] == 1
