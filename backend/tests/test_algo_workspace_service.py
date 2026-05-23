from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.datetime import utcnow
from app.core.exceptions import NotFoundError, ValidationError
from app.services import algo_workspace_service as algo_mod


@dataclass
class FakeDataset:
    id: str
    org_id: str
    created_by: str | None
    name: str
    modality: str = "image_text"
    status: str = "active"
    deleted_at: datetime | None = None


@dataclass
class FakeDatasetSample:
    id: str
    org_id: str
    dataset_id: str
    created_by: str | None
    sample_type: str = "text"
    sample_name: str | None = None
    text_content: str | None = None
    content_type: str | None = None
    size_bytes: int = 0
    checksum_sha256: str = ""
    quality_score: float | None = None
    annotation_data: dict | list | None = None
    related_entities: list | None = None
    source_metadata: dict | None = None
    preview_text: str | None = None
    file_url: str | None = None
    is_augmented: bool = False
    augmentation_source_id: str | None = None
    augmentation_method: str | None = None
    augmentation_params: dict | None = None
    created_at: datetime = datetime(2026, 5, 20, 10, 1, 0)
    deleted_at: datetime | None = None


@dataclass
class FakeResource:
    id: str
    org_id: str
    created_by: str | None
    name: str
    description: str | None = None
    status: str = "draft"
    config_json: dict | None = None
    result_summary: dict | None = None
    created_at: datetime = datetime(2026, 5, 20, 10, 0, 0)
    updated_at: datetime = datetime(2026, 5, 20, 10, 0, 0)
    deleted_at: datetime | None = None
    source_dataset_id: str | None = None
    sample_count: int = 0
    dataset_id: str | None = None
    eval_set_id: str | None = None
    model_config_id: str | None = None
    model_config: dict | None = None
    experiment_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    deployment_id: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    merge_mode: str = "dynamic"
    execution_mode: str | None = None
    executor_job_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    history_json: dict | None = None


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
    deleted_at: datetime | None = None
    created_at: datetime = datetime(2026, 5, 20, 10, 5, 0)


@dataclass
class FakeTask:
    id: str
    org_id: str
    product_id: str
    spec_code: str
    status: str = "done"


@dataclass
class FakeTaskResult:
    task_id: str
    org_id: str
    verdict: str | None = None
    overall_score: float | None = None


@dataclass
class FakeEvalItem:
    id: str
    org_id: str
    evaluation_dataset_id: str
    source_dataset_id: str
    dataset_sample_id: str | None
    created_by: str | None
    item_order: int
    payload_json: dict | None = None
    deleted_at: datetime | None = None
    created_at: datetime = datetime(2026, 5, 20, 10, 6, 0)
    updated_at: datetime = datetime(2026, 5, 20, 10, 6, 0)


class FakeDatasetRepo:
    def __init__(self, _session):
        self.rows = {
            "ds-1": FakeDataset(id="ds-1", org_id="org-1", created_by="user-1", name="dataset 1"),
            "ds-2": FakeDataset(id="ds-2", org_id="org-1", created_by="user-1", name="dataset 2", status="archived"),
        }

    async def get(self, *, org_id: str, dataset_id: str, owner_user_id: str):
        row = self.rows.get(dataset_id)
        if row and row.org_id == org_id and row.created_by == owner_user_id and row.deleted_at is None:
            return row
        return None

    async def recalculate_counters(self, *, dataset_id: str):
        return self.rows.get(dataset_id)


class FakeDatasetSampleRepo:
    def __init__(self, _session):
        self.rows = [
            FakeDatasetSample(
                id="sample-1",
                org_id="org-1",
                dataset_id="ds-1",
                created_by="user-1",
                sample_type="image",
                sample_name="screen-scratch.png",
                annotation_data={"labels": ["scratch", "screen"]},
                source_metadata={"defect": "scratch"},
                preview_text="screen-scratch.png",
                file_url="/uploads/screen-scratch.png",
            ),
            FakeDatasetSample(
                id="sample-2",
                org_id="org-1",
                dataset_id="ds-1",
                created_by="user-1",
                sample_type="text",
                sample_name="screen-note",
                text_content="屏幕存在划痕，需要返修处理",
                related_entities=["屏幕", "划痕"],
                preview_text="屏幕存在划痕，需要返修处理",
            ),
        ]

    async def list_for_dataset_all(self, *, org_id: str, dataset_id: str, owner_user_id: str):
        return [row for row in self.rows if row.org_id == org_id and row.dataset_id == dataset_id and row.created_by == owner_user_id and row.deleted_at is None]

    async def get(self, *, org_id: str, dataset_id: str, sample_id: str, owner_user_id: str):
        return next(
            (
                row
                for row in self.rows
                if row.id == sample_id and row.org_id == org_id and row.dataset_id == dataset_id and row.created_by == owner_user_id and row.deleted_at is None
            ),
            None,
        )

    async def create(self, payload: dict):
        row = FakeDatasetSample(id=f"sample-{len(self.rows) + 1}", **payload)
        self.rows.append(row)
        return row


class FakeDatasetJobRepo:
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


class FakeTaskRepo:
    def __init__(self, _session):
        self.rows = [
            FakeTask(id="task-1", org_id="org-1", product_id="p-1", spec_code="spec-a"),
            FakeTask(id="task-2", org_id="org-1", product_id="p-2", spec_code="spec-b"),
        ]

    async def list_paged(self, *, org_id: str, filters: dict | None, page: int, size: int, owner_user_id=None):
        rows = [row for row in self.rows if row.org_id == org_id and row.status == (filters or {}).get("status", row.status)]
        return rows[:size], len(rows)

    async def get(self, org_id: str, task_id: str):
        return next((row for row in self.rows if row.id == task_id and row.org_id == org_id), None)


class FakeTaskResultRepo:
    def __init__(self, _session):
        self.rows = {
            "task-1": FakeTaskResult(task_id="task-1", org_id="org-1", verdict="pass", overall_score=0.93),
            "task-2": FakeTaskResult(task_id="task-2", org_id="org-1", verdict="warn", overall_score=0.71),
        }

    async def get_by_task(self, org_id: str, task_id: str):
        row = self.rows.get(task_id)
        if row and row.org_id == org_id:
            return row
        return None


class FakeAlgoRepo:
    def __init__(self, _session):
        self.rows_by_model: dict[object, list[FakeResource]] = {}

    async def create(self, model, payload: dict):
        row = FakeResource(id=f"{getattr(model, '__name__', 'resource').lower()}-{len(self.rows_by_model.get(model, [])) + 1}", **payload)
        self.rows_by_model.setdefault(model, []).append(row)
        return row

    async def list_for_owner(self, *, model, org_id: str, owner_user_id: str, page: int, size: int, keyword: str | None = None, status: str | None = None, extra_filters=None):
        rows = [
            row for row in self.rows_by_model.get(model, [])
            if row.org_id == org_id and row.created_by == owner_user_id and row.deleted_at is None
        ]
        if status:
            rows = [row for row in rows if row.status == status]
        if keyword:
            rows = [row for row in rows if keyword in row.name]
        if extra_filters:
            for clause in extra_filters:
                field_name = str(clause.left.key)
                value = clause.right.value
                rows = [row for row in rows if getattr(row, field_name) == value]
        return rows[:size], len(rows)

    async def get(self, *, model, org_id: str, resource_id: str, owner_user_id: str):
        for row in self.rows_by_model.get(model, []):
            if row.id == resource_id and row.org_id == org_id and row.created_by == owner_user_id and row.deleted_at is None:
                return row
        return None

    async def save(self, obj, payload: dict):
        for key, value in payload.items():
            setattr(obj, key, value)
        return obj

    async def soft_delete(self, obj):
        obj.deleted_at = utcnow()
        return obj

    async def soft_delete_many(self, **kwargs):
        return None


class FakeEvalItemRepo:
    def __init__(self, _session):
        self.items: dict[str, list[FakeEvalItem]] = {}

    async def replace_items(self, *, org_id: str, evaluation_dataset_id: str, source_dataset_id: str, created_by: str, items: list[dict]):
        self.items[evaluation_dataset_id] = [
            FakeEvalItem(
                id=f"eval-item-{index + 1}",
                org_id=org_id,
                evaluation_dataset_id=evaluation_dataset_id,
                source_dataset_id=source_dataset_id,
                dataset_sample_id=item.get("dataset_sample_id"),
                created_by=created_by,
                item_order=index,
                payload_json=item.get("payload_json") or {},
            )
            for index, item in enumerate(items)
        ]

    async def count_items(self, *, org_id: str, evaluation_dataset_id: str, created_by: str):
        return len(self.items.get(evaluation_dataset_id, []))

    async def list_items(self, *, org_id: str, evaluation_dataset_id: str, created_by: str, page: int, size: int, sample_type: str | None = None):
        rows = [row for row in self.items.get(evaluation_dataset_id, []) if row.deleted_at is None]
        if sample_type:
            rows = [row for row in rows if (row.payload_json or {}).get("sample_type") == sample_type]
        return rows[:size], len(rows)

    async def list_items_all(self, *, org_id: str, evaluation_dataset_id: str, created_by: str):
        return [row for row in self.items.get(evaluation_dataset_id, []) if row.deleted_at is None]

    async def append_items(self, *, org_id: str, evaluation_dataset_id: str, source_dataset_id: str, created_by: str, items: list[dict]):
        existing = self.items.setdefault(evaluation_dataset_id, [])
        start = len(existing)
        existing.extend(
            [
                FakeEvalItem(
                    id=f"eval-item-{start + index + 1}",
                    org_id=org_id,
                    evaluation_dataset_id=evaluation_dataset_id,
                    source_dataset_id=source_dataset_id,
                    dataset_sample_id=item.get("dataset_sample_id"),
                    created_by=created_by,
                    item_order=start + index,
                    payload_json=item.get("payload_json") or {},
                )
                for index, item in enumerate(items)
            ]
        )

    async def get_item(self, *, org_id: str, evaluation_dataset_id: str, item_id: str, created_by: str):
        return next((row for row in self.items.get(evaluation_dataset_id, []) if row.id == item_id and row.deleted_at is None), None)

    async def soft_delete(self, obj):
        obj.deleted_at = utcnow()

    async def soft_delete_many(self, *, org_id: str, evaluation_dataset_id: str, created_by: str):
        for row in self.items.get(evaluation_dataset_id, []):
            row.deleted_at = utcnow()


class FakeKgRepo:
    def __init__(self, _session):
        self.entities = []
        self.relations = []

    async def list_entities(self, **kwargs):
        return list(self.entities)

    async def create_entity(self, payload: dict):
        row = FakeResource(
          id=f"entity-{len(self.entities) + 1}",
          org_id=payload["org_id"],
          created_by=payload["created_by"],
          name=payload["name"],
          description=payload.get("description"),
          dataset_id=payload["dataset_id"],
        )
        row.knowledge_graph_id = payload["knowledge_graph_id"]
        row.entity_type = payload["entity_type"]
        row.properties_json = payload.get("properties_json")
        row.confidence = payload.get("confidence")
        self.entities.append(row)
        return row

    async def get_entity(self, *, org_id: str, entity_id: str, created_by: str):
        return next((row for row in self.entities if row.id == entity_id and row.org_id == org_id and row.created_by == created_by), None)

    async def delete_entity(self, obj):
        obj.deleted_at = utcnow()

    async def list_relations(self, **kwargs):
        return list(self.relations)

    async def create_relation(self, payload: dict):
        row = FakeResource(
            id=f"relation-{len(self.relations) + 1}",
            org_id=payload["org_id"],
            created_by=payload["created_by"],
            name=payload["relation_type"],
            dataset_id=payload["dataset_id"],
        )
        row.knowledge_graph_id = payload["knowledge_graph_id"]
        row.source_entity_id = payload["source_entity_id"]
        row.target_entity_id = payload["target_entity_id"]
        row.relation_type = payload["relation_type"]
        row.properties_json = payload.get("properties_json")
        row.confidence = payload.get("confidence")
        self.relations.append(row)
        return row

    async def get_relation(self, *, org_id: str, relation_id: str, created_by: str):
        return next((row for row in self.relations if row.id == relation_id and row.org_id == org_id and row.created_by == created_by), None)

    async def delete_relation(self, obj):
        obj.deleted_at = utcnow()


class FakePairRepo:
    def __init__(self, _session):
        self.rows = []

    async def list_pairs(self, **kwargs):
        return list(self.rows)

    async def create_pair(self, payload: dict):
        row = FakeResource(
            id=f"pair-{len(self.rows) + 1}",
            org_id=payload["org_id"],
            created_by=payload["created_by"],
            name=payload["relation_type"],
            dataset_id=payload["dataset_id"],
        )
        row.alignment_id = payload["alignment_id"]
        row.source_sample_id = payload.get("source_sample_id")
        row.target_sample_id = payload.get("target_sample_id")
        row.relation_type = payload["relation_type"]
        row.similarity_score = payload.get("similarity_score")
        row.payload_json = payload.get("payload_json")
        row.confirmation_status = payload.get("confirmation_status", "suggested")
        self.rows.append(row)
        return row

    async def get_pair(self, *, org_id: str, pair_id: str, created_by: str):
        return next((row for row in self.rows if row.id == pair_id and row.org_id == org_id and row.created_by == created_by), None)

    async def delete_pair(self, obj):
        obj.deleted_at = utcnow()

    async def update_pair(self, obj, payload: dict):
        for key, value in payload.items():
            setattr(obj, key, value)
        return obj

    async def list_pairs_filtered(self, **kwargs):
        rows = [row for row in self.rows if row.deleted_at is None]
        if kwargs.get("only_confirmed"):
            rows = [row for row in rows if getattr(row, "confirmation_status", "suggested") == "confirmed"]
        return rows


class FakeProposalRepo:
    def __init__(self, _session):
        self.rows = []

    async def list_proposals(self, **kwargs):
        return list(self.rows)

    async def create_proposal(self, payload: dict):
        row = FakeResource(
            id=f"proposal-{len(self.rows) + 1}",
            org_id=payload["org_id"],
            created_by=payload["created_by"],
            name=payload["name"],
            description=payload.get("description"),
            status=payload.get("status", "draft"),
            config_json=payload.get("config_json"),
            result_summary=payload.get("result_summary"),
            dataset_id=payload["dataset_id"],
        )
        row.batch_id = payload["batch_id"]
        row.source_sample_id = payload.get("source_sample_id")
        row.augmentation_method = payload.get("augmentation_method")
        row.augmentation_params = payload.get("augmentation_params")
        self.rows.append(row)
        return row

    async def get_proposal(self, *, org_id: str, proposal_id: str, created_by: str):
        return next((row for row in self.rows if row.id == proposal_id and row.org_id == org_id and row.created_by == created_by), None)

    async def update_proposal(self, obj, payload: dict):
        for key, value in payload.items():
            setattr(obj, key, value)
        return obj

    async def delete_proposal(self, obj):
        obj.deleted_at = utcnow()

    async def list_history(self, *, org_id: str, dataset_id: str, created_by: str):
        return [row for row in self.rows if row.org_id == org_id and row.dataset_id == dataset_id and row.created_by == created_by and row.deleted_at is None]


class FakeSession:
    def __init__(self):
        self.commit_count = 0

    async def commit(self):
        self.commit_count += 1


class FakeModelConfig:
    def __init__(
        self,
        id: str,
        org_id: str,
        display_name: str,
        model_key: str,
        model_type: str = "chat",
        is_active: bool = True,
        provider: str = "openai",
        endpoint: str = "https://example.invalid/model",
        priority: int = 100,
        source_type: str = "external",
        source_uri: str | None = None,
        fine_tune_command_template: str | None = None,
        offline_eval_command_template: str | None = None,
        deployment_command_template: str | None = None,
        runtime_env_json: dict | None = None,
        default_gpu_request: int | None = None,
        default_cpu_request: int | None = None,
        default_memory_gb: int | None = None,
    ):
        self.id = id
        self.org_id = org_id
        self.display_name = display_name
        self.model_key = model_key
        self.model_type = model_type
        self.is_active = is_active
        self.provider = provider
        self.endpoint = endpoint
        self.priority = priority
        self.source_type = source_type
        self.source_uri = source_uri or f"{source_type}://{model_key}"
        self.fine_tune_command_template = fine_tune_command_template
        self.offline_eval_command_template = offline_eval_command_template
        self.deployment_command_template = deployment_command_template
        self.runtime_env_json = runtime_env_json
        self.default_gpu_request = default_gpu_request
        self.default_cpu_request = default_cpu_request
        self.default_memory_gb = default_memory_gb


class FakeModelConfigRepo:
    def __init__(self, _session):
        self.rows = {
            "mc-1": FakeModelConfig(id="mc-1", org_id="org-1", display_name="Train Model", model_key="train-model", model_type="chat"),
            "mc-2": FakeModelConfig(id="mc-2", org_id="org-1", display_name="Tune Model", model_key="tune-model", model_type="multimodal"),
            "mc-embed": FakeModelConfig(id="mc-embed", org_id="org-1", display_name="Embed Model", model_key="embed-model", model_type="embedding"),
        }

    async def get(self, org_id: str, config_id: str):
        row = self.rows.get(config_id)
        if row and row.org_id == org_id:
            return row
        return None

    async def list_active(self, org_id: str):
        return [row for row in self.rows.values() if row.org_id == org_id and row.is_active]


class FakeObjectStorage:
    backend_name = "local"

    def __init__(self):
        self.objects: dict[tuple[str, str], tuple[bytes, str | None]] = {}

    def ensure_bucket(self, bucket: str) -> None:
        return None

    def put_bytes(self, *, bucket: str, object_key: str, data: bytes, content_type: str | None = None):
        self.objects[(bucket, object_key)] = (data, content_type)
        return {
            "bucket": bucket,
            "object_key": object_key,
            "url": f"/storage/{object_key}",
            "size_bytes": len(data),
            "content_type": content_type,
        }

    def get_bytes(self, *, bucket: str, object_key: str):
        return self.objects.get((bucket, object_key))

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        return None

    def presign_download_url(self, *, bucket: str, object_key: str, expires_seconds: int = 3600) -> str:
        return f"/download/{object_key}"


class FakeGraphStore:
    enabled = True

    def __init__(self):
        self.entities: list[dict] = []
        self.relations: list[dict] = []
        self.resets: list[dict] = []
        self.deleted_entities: list[str] = []
        self.deleted_relations: list[str] = []

    def reset_graph(self, *, dataset_id: str, knowledge_graph_id: str) -> None:
        self.resets.append({"dataset_id": dataset_id, "knowledge_graph_id": knowledge_graph_id})

    def upsert_entity(self, payload) -> None:
        self.entities.append({key: getattr(payload, key) for key in payload.__slots__})

    def upsert_relation(self, payload) -> None:
        self.relations.append({key: getattr(payload, key) for key in payload.__slots__})

    def delete_entity(self, *, entity_id: str) -> None:
        self.deleted_entities.append(entity_id)

    def delete_relation(self, *, relation_id: str) -> None:
        self.deleted_relations.append(relation_id)


@pytest.fixture
def service(monkeypatch):
    session = FakeSession()
    dataset_repo = FakeDatasetRepo(None)
    sample_repo = FakeDatasetSampleRepo(None)
    job_repo = FakeDatasetJobRepo(None)
    algo_repo = FakeAlgoRepo(None)
    eval_item_repo = FakeEvalItemRepo(None)
    kg_repo = FakeKgRepo(None)
    pair_repo = FakePairRepo(None)
    proposal_repo = FakeProposalRepo(None)
    model_config_repo = FakeModelConfigRepo(None)
    task_repo = FakeTaskRepo(None)
    result_repo = FakeTaskResultRepo(None)
    object_storage = FakeObjectStorage()
    graph_store = FakeGraphStore()

    monkeypatch.setattr(algo_mod, "DatasetRepository", lambda session: dataset_repo)
    monkeypatch.setattr(algo_mod, "DatasetSampleRepository", lambda session: sample_repo)
    monkeypatch.setattr(algo_mod, "DatasetAsyncJobRepository", lambda session: job_repo)
    monkeypatch.setattr(algo_mod, "AlgoResourceRepository", lambda session: algo_repo)
    monkeypatch.setattr(algo_mod, "EvaluationDatasetItemRepository", lambda session: eval_item_repo)
    monkeypatch.setattr(algo_mod, "DatasetProcessingEntityRepository", lambda session: kg_repo)
    monkeypatch.setattr(algo_mod, "DatasetAlignmentPairRepository", lambda session: pair_repo)
    monkeypatch.setattr(algo_mod, "DatasetAugmentationProposalRepository", lambda session: proposal_repo)
    monkeypatch.setattr(algo_mod, "ModelConfigRepository", lambda session: model_config_repo)
    monkeypatch.setattr(algo_mod, "TaskRepository", lambda session: task_repo)
    monkeypatch.setattr(algo_mod, "ResultRepository", lambda session: result_repo)
    monkeypatch.setattr(algo_mod, "build_object_storage", lambda: object_storage)
    monkeypatch.setattr(algo_mod, "build_graph_store", lambda: graph_store)
    monkeypatch.setattr(algo_mod, "has_active_celery_worker", lambda: False)

    svc = algo_mod.AlgoWorkspaceService(session, "org-1", "user-1")
    return svc, algo_repo, eval_item_repo, job_repo, kg_repo, session, pair_repo, proposal_repo, sample_repo, dataset_repo


@pytest.mark.asyncio
async def test_create_eval_dataset_validates_samples_and_counts_items(service):
    svc, _algo_repo, eval_item_repo, _job_repo, _kg_repo, session, *_ = service

    created = await svc.create_evaluation_dataset(
        algo_mod.EvaluationDatasetCreateRequest(
            name="评测集 A",
            source_dataset_id="ds-1",
            sample_ids=["sample-1", "sample-2"],
        )
    )

    assert created.source_dataset_id == "ds-1"
    assert created.sample_count == 2
    assert eval_item_repo.items
    assert session.commit_count >= 1


@pytest.mark.asyncio
async def test_create_eval_dataset_rejects_foreign_sample(service):
    svc, *_ = service

    with pytest.raises(ValidationError):
        await svc.create_evaluation_dataset(
            algo_mod.EvaluationDatasetCreateRequest(
                name="bad",
                source_dataset_id="ds-1",
                sample_ids=["missing-sample"],
            )
        )


@pytest.mark.asyncio
async def test_create_fine_tune_requires_existing_dataset_and_persists_lora_config(service):
    svc, _algo_repo, _eval_item_repo, _job_repo, _kg_repo, session, *_ = service

    eval_set = await svc.create_evaluation_dataset(
        algo_mod.EvaluationDatasetCreateRequest(
            name="微调评测集",
            source_dataset_id="ds-1",
            sample_ids=["sample-1"],
        )
    )
    created = await svc.create_fine_tune(
        algo_mod.FineTuneRunCreateRequest(
            name="微调任务 1",
            source_dataset_id="ds-1",
            eval_set_id=eval_set.id,
            model_config_id="mc-1",
            config_json={
                "hyperparameters": {"epochs": 4, "learning_rate": 0.0002},
                "lora": {
                    "rank": 16,
                    "alpha": 32,
                    "target_modules": ["q_proj", "v_proj"],
                    "dropout": 0.05,
                },
            },
        )
    )

    assert created.source_dataset_id == "ds-1"
    assert created.eval_set_id == eval_set.id
    assert created.model_config_id == "mc-1"
    assert created.config_json is not None
    assert created.config_json["lora"]["rank"] == 16
    assert created.config_json["lora"]["target_modules"] == ["q_proj", "v_proj"]
    assert created.model_config_ref is not None
    assert created.model_config_ref.model_key == "train-model"
    assert created.status == "draft"
    assert session.commit_count >= 1


@pytest.mark.asyncio
async def test_create_fine_tune_rejects_inactive_dataset(service):
    svc, *_ = service

    with pytest.raises(ValidationError):
        await svc.create_fine_tune(
            algo_mod.FineTuneRunCreateRequest(
                name="微调任务 inactive",
                source_dataset_id="ds-2",
                model_config_id="mc-1",
            )
        )


@pytest.mark.asyncio
async def test_remaining_algo_resources_commit_and_validate_relations(service):
    svc, _algo_repo, _eval_item_repo, _job_repo, _kg_repo, session, *_ = service

    experiment = await svc.create_experiment(algo_mod.ExperimentCreateRequest(name="实验 A"))
    eval_set = await svc.create_evaluation_dataset(
        algo_mod.EvaluationDatasetCreateRequest(
            name="评测集 B",
            source_dataset_id="ds-1",
            sample_ids=["sample-1"],
        )
    )
    fine_tune = await svc.create_fine_tune(
        algo_mod.FineTuneRunCreateRequest(
            name="微调 A",
            source_dataset_id="ds-1",
            eval_set_id=eval_set.id,
            model_config_id="mc-2",
            experiment_id=experiment.id,
            config_json={"lora": {"rank": 8, "alpha": 16, "target_modules": ["q_proj"], "dropout": 0.1}},
        )
    )
    fine_tune_row = await svc._require_generic_resource(resource_type="fine_tune", resource_id=fine_tune.id)
    fine_tune_row.status = "completed"
    fine_tune_row.result_summary = {
        "summary": {
            "model_config_id": "mc-2",
            "model_key": "tune-model",
            "source_dataset_id": "ds-1",
            "eval_set_id": eval_set.id,
            "base_model_ref": {"display_name": "Tune Model", "source_type": "external", "source_uri": "external://tune-model"},
            "lora": {"rank": 8, "alpha": 16, "target_modules": ["q_proj"], "dropout": 0.1},
        },
        "artifacts": [{"type": "adapter", "path": "local://fine/adapter.safetensors"}],
        "metrics": {"summary": {"best_val_accuracy": 0.93}},
        "logs": [],
    }
    offline = await svc.create_offline_evaluation(
        algo_mod.OfflineEvaluationCreateRequest(
            name="离线评测 A",
            eval_set_id=eval_set.id,
            target_type="fine_tune",
            target_id=fine_tune.id,
            experiment_id=experiment.id,
        )
    )
    deployment = await svc.create_deployment(
        algo_mod.ModelDeploymentCreateRequest(
            name="部署 A",
            source_type="fine_tune",
            source_id=fine_tune.id,
            merge_mode="dynamic",
            experiment_id=experiment.id,
        )
    )
    deployment_row = await svc._require_generic_resource(resource_type="deployment", resource_id=deployment.id)
    deployment_row.status = "completed"
    deployment_row.result_summary = {
        "summary": {"source_type": "fine_tune", "source_id": fine_tune.id, "merge_mode": "dynamic"},
        "runtime_registration": {
            "source_type": "fine_tune",
            "source_id": fine_tune.id,
            "model_key": "tune-model",
            "provider": "openai",
            "endpoint_placeholder": "https://deployments.invalid/tune-model",
            "inference_config": {},
            "status": "registered",
        },
        "artifacts": [
            {"type": "adapter_bundle", "path": "local://fine/adapter.safetensors"},
            {"type": "deployment_manifest", "path": "local://deploy/manifest.json"},
        ],
        "logs": [],
    }
    online = await svc.create_online_validation(
        algo_mod.OnlineValidationCreateRequest(
            name="在线验证 A",
            deployment_id=deployment.id,
            experiment_id=experiment.id,
        )
    )

    assert fine_tune.source_dataset_id == "ds-1"
    assert fine_tune.model_config_id == "mc-2"
    assert fine_tune.eval_set_id == eval_set.id
    assert offline.target_id == fine_tune.id
    assert deployment.source_id == fine_tune.id
    assert deployment.merge_mode == "dynamic"
    assert online.deployment_id == deployment.id
    assert session.commit_count >= 6


@pytest.mark.asyncio
async def test_online_validation_requires_completed_deployment_and_stable_replay_summary(service):
    svc, _algo_repo, _eval_item_repo, _job_repo, _kg_repo, session, *_ = service

    fine_tune = await svc.create_fine_tune(
        algo_mod.FineTuneRunCreateRequest(
            name="微调任务 online",
            source_dataset_id="ds-1",
            model_config_id="mc-1",
            config_json={"lora": {"rank": 4, "alpha": 8, "target_modules": ["q_proj"], "dropout": 0.0}},
        )
    )
    fine_tune_row = await svc._require_generic_resource(resource_type="fine_tune", resource_id=fine_tune.id)
    fine_tune_row.status = "completed"
    fine_tune_row.result_summary = {
        "summary": {"model_config_id": "mc-1", "model_key": "train-model", "source_dataset_id": "ds-1"},
        "artifacts": [{"type": "adapter", "path": "local://fine/best-adapter.safetensors"}],
        "metrics": {"summary": {"best_val_accuracy": 0.91}},
        "logs": [],
    }

    deployment = await svc.create_deployment(
        algo_mod.ModelDeploymentCreateRequest(
            name="部署 B",
            source_type="fine_tune",
            source_id=fine_tune.id,
        )
    )

    with pytest.raises(ValidationError):
        await svc.create_online_validation(
            algo_mod.OnlineValidationCreateRequest(
                name="在线验证 B",
                deployment_id=deployment.id,
            )
        )

    deployment_row = await svc._require_generic_resource(resource_type="deployment", resource_id=deployment.id)
    deployment_row.status = "completed"
    deployment_row.result_summary = {
        "summary": {"source_type": "fine_tune", "source_id": fine_tune.id, "merge_mode": "dynamic"},
        "runtime_registration": {
            "source_type": "fine_tune",
            "source_id": fine_tune.id,
            "model_key": "train-model",
            "provider": "openai",
            "endpoint_placeholder": "https://deployments.invalid/train-model",
            "inference_config": {},
            "status": "registered",
        },
        "artifacts": [
            {"type": "adapter_bundle", "path": "local://fine/best-adapter.safetensors"},
            {"type": "deployment_manifest", "path": "local://deploy/manifest.json"},
        ],
        "logs": [],
    }

    online = await svc.create_online_validation(
        algo_mod.OnlineValidationCreateRequest(
            name="在线验证 C",
            deployment_id=deployment.id,
        )
    )
    launched = await svc.launch_generic_resource(resource_type="online_validation", resource_id=online.id)
    assert launched.status == "queued"

    await svc._run_online_validation_job(resource_id=online.id, mode="local_background")
    row = await svc.get_generic_resource(resource_type="online_validation", resource_id=online.id)
    summary = row.result_summary or {}
    assert summary["summary"]["deployment_id"] == deployment.id
    assert summary["summary"]["validation_type"] == "shadow"
    assert "replay_samples" in summary
    assert "metrics" in summary
    assert "logs" in summary
    assert row.status == "completed"
    assert session.commit_count >= 4


@pytest.mark.asyncio
async def test_experiment_detail_includes_related_resource_summary(service):
    svc, _algo_repo, _eval_item_repo, _job_repo, _kg_repo, session, *_ = service

    experiment = await svc.create_experiment(algo_mod.ExperimentCreateRequest(name="实验追踪"))

    fine_tune = await svc.create_fine_tune(
        algo_mod.FineTuneRunCreateRequest(
            name="微调任务 summary",
            source_dataset_id="ds-1",
            model_config_id="mc-2",
            experiment_id=experiment.id,
            config_json={"lora": {"rank": 8, "alpha": 16, "target_modules": ["q_proj"], "dropout": 0.1}},
        )
    )
    fine_row = await svc._require_generic_resource(resource_type="fine_tune", resource_id=fine_tune.id)
    fine_row.status = "completed"
    fine_row.result_summary = {
        "summary": {"status": "completed", "model_config_id": "mc-2", "source_dataset_id": "ds-1"},
        "artifacts": [{"type": "adapter", "path": "local://fine/best-adapter.safetensors"}],
        "metrics": {"summary": {"best_val_accuracy": 0.95}},
        "logs": [],
    }

    eval_set = await svc.create_evaluation_dataset(
        algo_mod.EvaluationDatasetCreateRequest(
            name="评测集 summary",
            source_dataset_id="ds-1",
            sample_ids=["sample-1"],
        )
    )

    offline = await svc.create_offline_evaluation(
        algo_mod.OfflineEvaluationCreateRequest(
            name="离线评测 summary",
            eval_set_id=eval_set.id,
            target_type="fine_tune",
            target_id=fine_tune.id,
            experiment_id=experiment.id,
        )
    )
    offline_row = await svc._require_generic_resource(resource_type="offline_evaluation", resource_id=offline.id)
    offline_row.status = "completed"
    offline_row.result_summary = {
        "summary": {"status": "completed", "target_id": fine_tune.id},
        "metrics": {"accuracy": 0.89, "f1": 0.91},
        "error_cases": [],
        "artifacts": [],
        "logs": [],
    }

    deployment = await svc.create_deployment(
        algo_mod.ModelDeploymentCreateRequest(
            name="部署 summary",
            source_type="fine_tune",
            source_id=fine_tune.id,
            merge_mode="static",
            experiment_id=experiment.id,
        )
    )
    deployment_row = await svc._require_generic_resource(resource_type="deployment", resource_id=deployment.id)
    deployment_row.status = "completed"
    deployment_row.result_summary = {
        "summary": {"source_type": "fine_tune", "source_id": fine_tune.id, "merge_mode": "static"},
        "runtime_registration": {
            "source_type": "fine_tune",
            "source_id": fine_tune.id,
            "model_key": "fine-model",
            "provider": "openai",
            "endpoint_placeholder": "https://deployments.invalid/fine-model",
            "inference_config": {},
            "status": "registered",
        },
        "artifacts": [
            {"type": "merged_model", "path": "local://deploy/merged-model.bin"},
            {"type": "deployment_manifest", "path": "local://deploy/manifest.json"},
        ],
        "logs": [],
    }

    response = await svc.get_generic_resource(resource_type="experiment", resource_id=experiment.id)
    summary = response.result_summary or {}
    related = response.related_resources

    assert summary["summary"]["微调任务数"] == 1
    assert summary["summary"]["离线评测数"] == 1
    assert summary["summary"]["部署数"] == 1
    assert len(related.fine_tunes) == 1
    assert len(related.offline_evaluations) == 1
    assert len(related.deployments) == 1
    assert session.commit_count >= 5


@pytest.mark.asyncio
async def test_fine_tune_rejects_embedding_model_config(service):
    svc, *_ = service

    with pytest.raises(ValidationError):
        await svc.create_fine_tune(
            algo_mod.FineTuneRunCreateRequest(
                name="微调 embed",
                source_dataset_id="ds-1",
                model_config_id="mc-embed",
            )
        )


@pytest.mark.asyncio
async def test_generic_launch_cancel_commits_for_execution_resources(service):
    svc, _algo_repo, _eval_item_repo, _job_repo, _kg_repo, session, *_ = service
    experiment = await svc.create_experiment(algo_mod.ExperimentCreateRequest(name="实验 C"))

    launched = await svc.launch_generic_resource(resource_type="experiment", resource_id=experiment.id)
    assert launched.status == "queued"

    cancelled = await svc.cancel_generic_resource(resource_type="experiment", resource_id=experiment.id)
    assert cancelled.status == "cancelled"
    assert session.commit_count >= 3


@pytest.mark.asyncio
async def test_launch_generic_resource_marks_queued(service, monkeypatch):
    svc, algo_repo, *_ = service
    monkeypatch.setattr(algo_mod, "has_active_celery_worker", lambda: False)
    created = await svc.create_experiment(algo_mod.ExperimentCreateRequest(name="实验 1"))

    result = await svc.launch_generic_resource(resource_type="experiment", resource_id=created.id)

    assert result.status == "queued"
    row = await svc.get_generic_resource(resource_type="experiment", resource_id=created.id)
    assert row.status == "queued"


@pytest.mark.asyncio
async def test_cancel_generic_resource_rejects_draft(service):
    svc, *_ = service
    created = await svc.create_experiment(algo_mod.ExperimentCreateRequest(name="实验 2"))

    with pytest.raises(ValidationError):
        await svc.cancel_generic_resource(resource_type="experiment", resource_id=created.id)


@pytest.mark.asyncio
async def test_launch_processing_run_creates_job(service, monkeypatch):
    svc, _algo_repo, _eval_item_repo, job_repo, _kg_repo, *_ = service
    monkeypatch.setattr(algo_mod, "has_active_celery_worker", lambda: False)

    status = await svc.launch_processing_run(
        dataset_id="ds-1",
        processing_type="kg",
        payload=algo_mod.DatasetProcessingRunRequest(name="kg run"),
    )

    assert status.resource is not None
    assert status.resource.status == "queued"
    assert job_repo.jobs[-1].job_type == "knowledge_graph_build"


@pytest.mark.asyncio
async def test_create_export_preserves_selected_format_in_config(service, monkeypatch):
    svc, _algo_repo, _eval_item_repo, job_repo, _kg_repo, *_ = service
    monkeypatch.setattr(algo_mod, "has_active_celery_worker", lambda: False)

    created = await svc.create_export(
        dataset_id="ds-1",
        payload=algo_mod.DatasetExportRequest(
            name="export run",
            format="coco",
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            include_augmented=True,
            only_confirmed_alignment=False,
        ),
    )

    assert created.config_json is not None
    assert created.config_json["format"] == "coco"
    assert "config_json" not in created.config_json
    assert job_repo.jobs[-1].job_type == "dataset_export"


@pytest.mark.asyncio
async def test_get_export_results_rewrites_download_url_to_api_route(service, monkeypatch):
    svc, _algo_repo, _eval_item_repo, _job_repo, _kg_repo, *_ = service
    monkeypatch.setattr(algo_mod, "has_active_celery_worker", lambda: False)

    await svc.create_export(
        dataset_id="ds-1",
        payload=algo_mod.DatasetExportRequest(name="export run", format="yolo"),
    )
    resource = await svc._require_processing_resource(dataset_id="ds-1", processing_type="export")
    resource.status = "completed"
    resource.result_summary = {
        "artifact": {
            "bucket": "dataset-exports",
            "object_key": "dataset-exports/org-1/ds-1/export-1/labels.yolo.json",
            "download_url": "http://minio:9000/dataset-exports/org-1/ds-1/export-1/labels.yolo.json",
            "format": "yolo",
        }
    }

    result = await svc.get_processing_results(dataset_id="ds-1", processing_type="export")

    assert result.artifact is not None
    assert result.artifact["format"] == "yolo"
    assert result.artifact["download_url"] == "/api/v1/datasets/ds-1/exports/download"
    assert isinstance(result.summary, dict)
    assert result.summary["artifact"]["download_url"] == "/api/v1/datasets/ds-1/exports/download"


@pytest.mark.asyncio
async def test_export_pipeline_records_storage_backend(service, monkeypatch):
    svc, _algo_repo, _eval_item_repo, _job_repo, _kg_repo, *_ = service
    monkeypatch.setattr(algo_mod, "has_active_celery_worker", lambda: False)

    summary = await svc._processing.run_export_build(
        dataset_id="ds-1",
        resource_id="export-1",
        dataset=svc._datasets.rows["ds-1"],
        config_json={"format": "coco"},
        alignment_resource_id=None,
    )

    assert summary["artifact"]["storage_backend"] == "local"


def test_get_export_artifact_payload_uses_minio_backend_fallback(service, monkeypatch):
    svc, *_ = service

    class FakeMinioStorage:
        backend_name = "minio"

        def __init__(self, *, endpoint: str, access_key: str, secret_key: str):
            self.endpoint = endpoint
            self.access_key = access_key
            self.secret_key = secret_key

        def get_bytes(self, *, bucket: str, object_key: str):
            return (b'{"format":"coco"}', "application/json")

    monkeypatch.setattr(algo_mod, "MinioObjectStorage", FakeMinioStorage)

    payload = svc.get_export_artifact_payload(
        bucket="dataset-exports",
        object_key="dataset-exports/org-1/ds-1/export-1/annotations.coco.json",
        storage_backend="minio",
    )

    assert payload == (b'{"format":"coco"}', "application/json")


def test_get_export_artifact_payload_falls_back_to_local_legacy_file(service, monkeypatch, tmp_path):
    svc, *_ = service

    legacy_dir = tmp_path / "dataset-exports/org-1/ds-1/export-1"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_dir / "legacy-random.json"
    legacy_file.write_bytes(b'{"format":"legacy"}')

    class FakeLegacyLocalStorage:
        backend_name = "local"

        def get_bytes(self, *, bucket: str, object_key: str):
            return None

        def get_bytes_from_legacy_prefix(self, *, object_key_prefix: str, suffix: str | None = None):
            if object_key_prefix == "dataset-exports/org-1/ds-1/export-1":
                return legacy_file.read_bytes(), "application/json"
            return None

    svc._storage = FakeLegacyLocalStorage()

    payload = svc.get_export_artifact_payload(
        bucket="dataset-exports",
        object_key="dataset-exports/org-1/ds-1/export-1/annotations.coco.json",
        storage_backend="local",
    )

    assert payload == (b'{"format":"legacy"}', "application/json")


@pytest.mark.asyncio
async def test_create_kg_relation_requires_existing_entities(service):
    svc, _algo_repo, _eval_item_repo, _job_repo, kg_repo, *_ = service
    await svc.launch_processing_run(
        dataset_id="ds-1",
        processing_type="kg",
        payload=algo_mod.DatasetProcessingRunRequest(name="kg run"),
    )
    resource = await svc._require_processing_resource(dataset_id="ds-1", processing_type="kg")
    resource.status = "failed"
    entity = await svc.create_kg_entity(
        dataset_id="ds-1",
        payload=algo_mod.DatasetKgEntityCreateRequest(name="实体 1", entity_type="Defect"),
    )

    created = await svc.create_kg_relation(
        dataset_id="ds-1",
        payload=algo_mod.DatasetKgRelationCreateRequest(
            source_entity_id=entity.id,
            target_entity_id=entity.id,
            relation_type="RELATED_TO",
        ),
    )

    assert created.relation_type == "RELATED_TO"
    assert kg_repo.relations


@pytest.mark.asyncio
async def test_get_generic_resource_not_found(service):
    svc, *_ = service

    with pytest.raises(NotFoundError):
        await svc.get_generic_resource(resource_type="experiment", resource_id="missing")


@pytest.mark.asyncio
async def test_create_fine_tune_rejects_missing_eval_set(service):
    svc, *_ = service
    with pytest.raises(NotFoundError):
        await svc.create_fine_tune(
            algo_mod.FineTuneRunCreateRequest(
                name="微调失败",
                source_dataset_id="ds-1",
                eval_set_id="missing-eval",
                model_config_id="mc-2",
            )
        )


@pytest.mark.asyncio
async def test_create_offline_evaluation_rejects_incomplete_target(service):
    svc, *_ = service
    eval_set = await svc.create_evaluation_dataset(
        algo_mod.EvaluationDatasetCreateRequest(
            name="评测集 C",
            source_dataset_id="ds-1",
            sample_ids=["sample-1"],
        )
    )

    with pytest.raises(NotFoundError):
        await svc.create_offline_evaluation(
            algo_mod.OfflineEvaluationCreateRequest(
                name="离线评测失败",
                eval_set_id=eval_set.id,
                target_type="fine_tune",
                target_id="missing-fine-tune",
            )
        )


@pytest.mark.asyncio
async def test_create_deployment_rejects_non_fine_tune_source_and_missing_artifact(service):
    svc, *_ = service
    fine_tune = await svc.create_fine_tune(
        algo_mod.FineTuneRunCreateRequest(
            name="微调 deploy",
            source_dataset_id="ds-1",
            model_config_id="mc-1",
        )
    )
    fine_tune_row = await svc._require_generic_resource(resource_type="fine_tune", resource_id=fine_tune.id)
    fine_tune_row.status = "completed"
    fine_tune_row.result_summary = {"artifacts": [], "metrics": {}, "logs": []}

    with pytest.raises(PydanticValidationError):
        algo_mod.ModelDeploymentCreateRequest(
            name="部署失败1",
            source_type="deployment",
            source_id="dp-1",
        )

    with pytest.raises(ValidationError):
        await svc.create_deployment(
            algo_mod.ModelDeploymentCreateRequest(
                name="部署失败2",
                source_type="fine_tune",
                source_id=fine_tune.id,
            )
        )

    fine_tune_row.result_summary = {
        "summary": {"model_config_id": "mc-1", "model_key": "train-model"},
        "artifacts": [{"type": "adapter", "path": "local://fine/adapter.safetensors"}],
        "metrics": {"summary": {"best_val_accuracy": 0.91}},
        "logs": [],
    }
    created = await svc.create_deployment(
        algo_mod.ModelDeploymentCreateRequest(
            name="部署成功",
            source_type="fine_tune",
            source_id=fine_tune.id,
            merge_mode="static",
        )
    )
    assert created.source_type == "fine_tune"
    assert created.merge_mode == "static"


@pytest.mark.asyncio
async def test_create_alignment_pair_confirms_manual_rows_and_validates_sample_types(service):
    svc, *_ = service
    await svc.launch_processing_run(
        dataset_id="ds-1",
        processing_type="alignment",
        payload=algo_mod.DatasetProcessingRunRequest(name="alignment run"),
    )
    resource = await svc._require_processing_resource(dataset_id="ds-1", processing_type="alignment")
    resource.status = "failed"

    created = await svc.create_alignment_pair(
        dataset_id="ds-1",
        payload=algo_mod.DatasetAlignmentPairCreateRequest(
            source_sample_id="sample-1",
            target_sample_id="sample-2",
            relation_type="describes",
            similarity_score=0.88,
        ),
    )

    assert created.confirmation_status == "confirmed"
    assert created.payload_json["source"] == "manual"


@pytest.mark.asyncio
async def test_manual_editing_rejects_running_processing_resources(service):
    svc, *_ = service
    await svc.launch_processing_run(
        dataset_id="ds-1",
        processing_type="kg",
        payload=algo_mod.DatasetProcessingRunRequest(name="kg run"),
    )
    resource = await svc._require_processing_resource(dataset_id="ds-1", processing_type="kg")
    resource.status = "running"

    with pytest.raises(ValidationError):
        await svc.create_kg_entity(
            dataset_id="ds-1",
            payload=algo_mod.DatasetKgEntityCreateRequest(name="实体 1", entity_type="Defect"),
        )


@pytest.mark.asyncio
async def test_alignment_can_use_explicit_embedding_model_config(service):
    svc, *_ = service
    await svc.launch_processing_run(
        dataset_id="ds-1",
        processing_type="alignment",
        payload=algo_mod.DatasetProcessingRunRequest(name="alignment run", config_json={"embedding_model_id": "mc-embed"}),
    )
    status = await svc.get_processing_status(dataset_id="ds-1", processing_type="alignment")
    assert status.resource is not None


@pytest.mark.asyncio
async def test_apply_augmentation_creates_augmented_samples_and_history(service):
    svc, _algo_repo, _eval_item_repo, _job_repo, _kg_repo, _session, _pair_repo, proposal_repo, sample_repo, *_ = service
    await svc.launch_processing_run(
        dataset_id="ds-1",
        processing_type="augmentation",
        payload=algo_mod.DatasetProcessingRunRequest(name="augmentation run"),
    )
    resource = await svc._require_processing_resource(dataset_id="ds-1", processing_type="augmentation")
    resource.status = "failed"
    proposal = await svc.create_augmentation_proposal(
        dataset_id="ds-1",
        payload=algo_mod.DatasetAugmentationProposalCreateRequest(
            name="proposal-1",
            description="屏幕存在划痕，需要返修处理",
            source_sample_id="sample-2",
            augmentation_method="entity_substitution",
            augmentation_params={"mode": "demo"},
        ),
    )

    result = await svc.apply_augmentation(dataset_id="ds-1", proposal_ids=[proposal.id])
    history = await svc.get_augmentation_history(dataset_id="ds-1")

    assert result["created_sample_ids"]
    assert sample_repo.rows[-1].is_augmented is True
    assert sample_repo.rows[-1].augmentation_source_id == "sample-2"
    assert proposal_repo.rows[0].status == "completed"
    assert history["history"][0]["created_sample_id"] == result["created_sample_ids"][0]


@pytest.mark.asyncio
async def test_delete_generic_resource_rejects_running_status(service):
    svc, *_ = service
    fine_tune = await svc.create_fine_tune(
        algo_mod.FineTuneRunCreateRequest(
            name="微调任务 running",
            source_dataset_id="ds-1",
            model_config_id="mc-1",
        )
    )
    row = await svc._require_generic_resource(resource_type="fine_tune", resource_id=fine_tune.id)
    row.status = "running"

    with pytest.raises(ValidationError):
        await svc.delete_generic_resource(resource_type="fine_tune", resource_id=fine_tune.id)


@pytest.mark.asyncio
async def test_snapshot_items_survive_source_sample_deletion(service):
    svc, _algo_repo, eval_item_repo, _job_repo, _kg_repo, _session, _pair_repo, _proposal_repo, sample_repo, *_ = service
    created = await svc.create_evaluation_dataset(
        algo_mod.EvaluationDatasetCreateRequest(
            name="评测集 snapshot",
            source_dataset_id="ds-1",
            sample_ids=["sample-1"],
        )
    )
    sample_repo.rows = [row for row in sample_repo.rows if row.id != "sample-1"]
    items = await svc.list_evaluation_dataset_items(resource_id=created.id, page=1, size=10)

    assert items.items[0].snapshot_deleted_from_source is True
    assert items.items[0].sample_name == "screen-scratch.png"
    assert eval_item_repo.items


@pytest.mark.asyncio
async def test_experiment_detail_includes_related_resources(service):
    svc, *_ = service
    experiment = await svc.create_experiment(algo_mod.ExperimentCreateRequest(name="实验聚合"))
    fine_tune = await svc.create_fine_tune(
        algo_mod.FineTuneRunCreateRequest(
            name="微调任务聚合",
            source_dataset_id="ds-1",
            model_config_id="mc-1",
            experiment_id=experiment.id,
        )
    )
    row = await svc._require_generic_resource(resource_type="fine_tune", resource_id=fine_tune.id)
    row.status = "completed"
    row.result_summary = {
        "summary": {"model_config_id": "mc-1", "model_key": "train-model", "source_dataset_id": "ds-1"},
        "artifacts": [{"type": "adapter", "path": "local://fine/best-adapter.safetensors"}],
        "metrics": {"summary": {"best_val_accuracy": 0.92}},
        "logs": [],
    }

    detail = await svc.get_generic_resource(resource_type="experiment", resource_id=experiment.id)

    assert detail.related_resources.fine_tunes
    assert detail.related_resources.fine_tunes[0].id == fine_tune.id


@pytest.mark.asyncio
async def test_p0_chain_create_flow_success(service):
    svc, *_ = service
    eval_set = await svc.create_evaluation_dataset(
        algo_mod.EvaluationDatasetCreateRequest(
            name="评测集链路",
            source_dataset_id="ds-1",
            sample_ids=["sample-1", "sample-2"],
        )
    )
    fine_tune = await svc.create_fine_tune(
        algo_mod.FineTuneRunCreateRequest(
            name="微调链路",
            source_dataset_id="ds-1",
            eval_set_id=eval_set.id,
            model_config_id="mc-2",
            config_json={"lora": {"rank": 8, "alpha": 16, "target_modules": ["q_proj"], "dropout": 0.1}},
        )
    )
    fine_tune_row = await svc._require_generic_resource(resource_type="fine_tune", resource_id=fine_tune.id)
    fine_tune_row.status = "completed"
    fine_tune_row.result_summary = {
        "summary": {"model_config_id": "mc-2", "model_key": "tune-model", "source_dataset_id": "ds-1", "eval_set_id": eval_set.id},
        "artifacts": [{"type": "adapter", "path": "local://fine/adapter.safetensors"}],
        "metrics": {"summary": {"best_val_accuracy": 0.93}},
        "logs": [],
    }
    offline = await svc.create_offline_evaluation(
        algo_mod.OfflineEvaluationCreateRequest(
            name="离线评测链路",
            eval_set_id=eval_set.id,
            target_type="fine_tune",
            target_id=fine_tune.id,
        )
    )
    deployment = await svc.create_deployment(
        algo_mod.ModelDeploymentCreateRequest(
            name="部署链路",
            source_type="fine_tune",
            source_id=fine_tune.id,
            merge_mode="dynamic",
        )
    )

    assert eval_set.sample_count == 2
    assert fine_tune.source_dataset_id == "ds-1"
    assert fine_tune.eval_set_id == eval_set.id
    assert offline.target_id == fine_tune.id
    assert deployment.source_id == fine_tune.id
    assert deployment.merge_mode == "dynamic"


@pytest.mark.asyncio
async def test_execution_helpers_generate_stable_result_summary_structures():
    fine_tune_summary = algo_mod.TrainingRunner.run_fine_tune(
        resource_id="ft-1",
        resource_name="微调任务",
        source_dataset_id="ds-1",
        eval_set_id="eval-1",
        model_ref=algo_mod.ExecutionModelRef(
            id="mc-2",
            provider="openai",
            model_key="tune-model",
            display_name="Tune Model",
            endpoint="https://example.invalid/tune",
            source_type="external",
            source_uri="external://tune-model",
            model_type="multimodal",
        ),
        config_json={
            "hyperparameters": {"epochs": 2},
            "lora": {"rank": 8, "alpha": 16, "target_modules": ["q_proj", "v_proj"], "dropout": 0.05},
        },
        execution_mode="local_background",
        started_at=datetime(2026, 5, 21, 10, 10, 0),
        completed_at=datetime(2026, 5, 21, 10, 12, 0),
    )
    assert fine_tune_summary["summary"]["source_dataset_id"] == "ds-1"
    assert fine_tune_summary["summary"]["eval_set_id"] == "eval-1"
    assert fine_tune_summary["summary"]["base_model_ref"]["source_uri"] == "external://tune-model"
    assert fine_tune_summary["summary"]["lora"]["target_modules"] == ["q_proj", "v_proj"]
    assert fine_tune_summary["artifacts"][0]["type"] == "adapter"

    offline_summary = algo_mod.EvaluationEngine.run_offline_evaluation(
        resource_id="oe-1",
        resource_name="离线评测",
        eval_set_id="eval-1",
        sample_count=3,
        target_type="fine_tune",
        target_id="ft-1",
        target_summary=fine_tune_summary,
        config_json={"metrics": ["accuracy", "f1"]},
        execution_mode="local_background",
        started_at=datetime(2026, 5, 21, 10, 20, 0),
        completed_at=datetime(2026, 5, 21, 10, 22, 0),
    )
    assert offline_summary["metrics"]["accuracy"] > 0
    assert offline_summary["error_cases"]

    deployment_summary = algo_mod.DeploymentManager.run_deployment(
        resource_id="dp-1",
        resource_name="部署任务",
        source_type="fine_tune",
        source_id="ft-1",
        merge_mode="static",
        source_summary=fine_tune_summary,
        model_ref=algo_mod.ExecutionModelRef(
            id="mc-2",
            provider="openai",
            model_key="tune-model",
            display_name="Tune Model",
            endpoint="https://example.invalid/tune",
            source_type="external",
            source_uri="external://tune-model",
            model_type="multimodal",
        ),
        config_json={"service_config": {"max_batch_size": 8, "max_concurrency": 16, "timeout_ms": 5000}},
        execution_mode="local_background",
        started_at=datetime(2026, 5, 21, 10, 30, 0),
        completed_at=datetime(2026, 5, 21, 10, 35, 0),
    )
    assert deployment_summary["runtime_registration"]["status"] == "available"
    assert deployment_summary["summary"]["merge_mode"] == "static"
    assert deployment_summary["artifacts"][0]["type"] == "merged_model"


@pytest.mark.asyncio
async def test_update_gpu_running_summary_persists_remote_poll_diagnostics(service):
    svc, algo_repo, _eval_item_repo, _job_repo, _kg_repo, _session, *_ = service

    row = await algo_repo.create(
        model=algo_mod.FineTuneRun,
        payload={
            "org_id": "org-1",
            "created_by": "user-1",
            "name": "gpu ft",
            "status": "running",
            "execution_mode": "gpu_ssh",
            "result_summary": {
                "summary": {"status": "running"},
                "remote_execution": {"host": "10.0.0.10"},
                "logs": [],
            },
        },
    )

    await svc._update_gpu_running_summary(
        row=row,
        summary=dict(row.result_summary or {}),
        remote_status={
            "status": "running",
            "status_file_state": "ok",
            "poll_error": "temporary ssh read error",
            "log_tail": "tail output",
            "exit_code": 0,
        },
    )

    remote = row.result_summary["remote_execution"]
    assert remote["last_remote_status"] == "running"
    assert remote["status_file_state"] == "ok"
    assert remote["poll_error"] == "temporary ssh read error"
    assert remote["last_log_tail"] == "tail output"
    assert remote["poll_fail_count"] == 1
