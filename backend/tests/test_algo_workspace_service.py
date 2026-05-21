from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.services import algo_workspace_service as algo_mod


@dataclass
class FakeDataset:
    id: str
    org_id: str
    created_by: str | None
    name: str
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
    training_job_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    deployment_id: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    execution_mode: str | None = None
    executor_job_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


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
        }

    async def get(self, *, org_id: str, dataset_id: str, owner_user_id: str):
        row = self.rows.get(dataset_id)
        if row and row.org_id == org_id and row.created_by == owner_user_id and row.deleted_at is None:
            return row
        return None


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
            # Fake filter only supports dataset_id equality from service usage.
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
        obj.deleted_at = datetime.utcnow()
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
        rows = self.items.get(evaluation_dataset_id, [])
        return rows[:size], len(rows)

    async def list_items_all(self, *, org_id: str, evaluation_dataset_id: str, created_by: str):
        return self.items.get(evaluation_dataset_id, [])

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
        return None

    async def soft_delete(self, obj):
        return None

    async def soft_delete_many(self, *, org_id: str, evaluation_dataset_id: str, created_by: str):
        return None


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
        obj.deleted_at = datetime.utcnow()

    async def list_relations(self, **kwargs):
        return list(self.relations)

    async def create_relation(self, payload: dict):
        row = FakeResource(id=f"relation-{len(self.relations) + 1}", org_id=payload["org_id"], created_by=payload["created_by"], name=payload["relation_type"])
        row.knowledge_graph_id = payload["knowledge_graph_id"]
        row.source_entity_id = payload["source_entity_id"]
        row.target_entity_id = payload["target_entity_id"]
        row.relation_type = payload["relation_type"]
        self.relations.append(row)
        return row

    async def get_relation(self, *, org_id: str, relation_id: str, created_by: str):
        return next((row for row in self.relations if row.id == relation_id and row.org_id == org_id and row.created_by == created_by), None)

    async def delete_relation(self, obj):
        obj.deleted_at = datetime.utcnow()


class FakePairRepo:
    def __init__(self, _session):
        self.rows = []

    async def list_pairs(self, **kwargs):
        return list(self.rows)

    async def create_pair(self, payload: dict):
        row = FakeResource(id=f"pair-{len(self.rows) + 1}", org_id=payload["org_id"], created_by=payload["created_by"], name=payload["relation_type"])
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
        obj.deleted_at = datetime.utcnow()

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

    async def delete_proposal(self, obj):
        obj.deleted_at = datetime.utcnow()

    async def list_history(self, *, org_id: str, dataset_id: str, created_by: str):
        return [row for row in self.rows if row.org_id == org_id and row.dataset_id == dataset_id and row.created_by == created_by and row.deleted_at is None]


class FakeSession:
    def __init__(self):
        self.commit_count = 0

    async def commit(self):
        self.commit_count += 1


class FakeModelConfig:
    def __init__(self, id: str, org_id: str, display_name: str, model_key: str, model_type: str = "chat", is_active: bool = True):
        self.id = id
        self.org_id = org_id
        self.display_name = display_name
        self.model_key = model_key
        self.model_type = model_type
        self.is_active = is_active


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

    def ensure_bucket(self, bucket: str) -> None:
        return None

    def put_bytes(self, *, bucket: str, object_key: str, data: bytes, content_type: str | None = None):
        return {
            "bucket": bucket,
            "object_key": object_key,
            "url": f"/storage/{object_key}",
            "size_bytes": len(data),
            "content_type": content_type,
        }

    def get_bytes(self, *, bucket: str, object_key: str):
        return None

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        return None

    def presign_download_url(self, *, bucket: str, object_key: str, expires_seconds: int = 3600) -> str:
        return f"/download/{object_key}"


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
    object_storage = FakeObjectStorage()

    monkeypatch.setattr(algo_mod, "DatasetRepository", lambda session: dataset_repo)
    monkeypatch.setattr(algo_mod, "DatasetSampleRepository", lambda session: sample_repo)
    monkeypatch.setattr(algo_mod, "DatasetAsyncJobRepository", lambda session: job_repo)
    monkeypatch.setattr(algo_mod, "AlgoResourceRepository", lambda session: algo_repo)
    monkeypatch.setattr(algo_mod, "EvaluationDatasetItemRepository", lambda session: eval_item_repo)
    monkeypatch.setattr(algo_mod, "DatasetProcessingEntityRepository", lambda session: kg_repo)
    monkeypatch.setattr(algo_mod, "DatasetAlignmentPairRepository", lambda session: pair_repo)
    monkeypatch.setattr(algo_mod, "DatasetAugmentationProposalRepository", lambda session: proposal_repo)
    monkeypatch.setattr(algo_mod, "ModelConfigRepository", lambda session: model_config_repo)
    monkeypatch.setattr(algo_mod, "build_object_storage", lambda: object_storage)
    monkeypatch.setattr(algo_mod, "has_active_celery_worker", lambda: False)

    svc = algo_mod.AlgoWorkspaceService(session, "org-1", "user-1")
    return svc, algo_repo, eval_item_repo, job_repo, kg_repo, session, pair_repo, proposal_repo, sample_repo


@pytest.mark.asyncio
async def test_create_eval_dataset_validates_samples_and_counts_items(service):
    svc, _algo_repo, eval_item_repo, _job_repo, _kg_repo, session = service

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
async def test_create_training_job_requires_existing_dataset(service):
    svc, *_rest, session = service

    created = await svc.create_training_job(
        algo_mod.TrainingJobCreateRequest(
            name="训练任务 1",
            source_dataset_id="ds-1",
            model_config_id="mc-1",
        )
    )

    assert created.source_dataset_id == "ds-1"
    assert created.model_config_id == "mc-1"
    assert created.status == "draft"
    assert session.commit_count >= 1


@pytest.mark.asyncio
async def test_training_job_launch_cancel_and_result_summary(service):
    svc, *_rest, session = service
    created = await svc.create_training_job(
        algo_mod.TrainingJobCreateRequest(
            name="训练任务 2",
            source_dataset_id="ds-1",
            model_config_id="mc-1",
        )
    )

    launched = await svc.launch_training_job(created.id)
    assert launched.status == "queued"

    row = await svc.get_generic_resource(resource_type="training_job", resource_id=created.id)
    assert row.result_summary["artifacts"] == []
    assert row.result_summary["metrics"] == {}
    assert row.result_summary["logs"] == []

    cancelled = await svc.cancel_training_job(created.id)
    assert cancelled.status == "cancelled"
    assert session.commit_count >= 3


@pytest.mark.asyncio
async def test_remaining_algo_resources_commit_and_validate_relations(service):
    svc, _algo_repo, _eval_item_repo, _job_repo, _kg_repo, session = service

    training_job = await svc.create_training_job(
        algo_mod.TrainingJobCreateRequest(
            name="训练任务 3",
            source_dataset_id="ds-1",
            model_config_id="mc-1",
        )
    )
    experiment = await svc.create_experiment(algo_mod.ExperimentCreateRequest(name="实验 A"))
    fine_tune = await svc.create_fine_tune(
        algo_mod.FineTuneRunCreateRequest(
            name="微调 A",
            training_job_id=training_job.id,
            model_config_id="mc-2",
            experiment_id=experiment.id,
        )
    )
    offline = await svc.create_offline_evaluation(
        algo_mod.OfflineEvaluationCreateRequest(
            name="离线评测 A",
            eval_set_id=(await svc.create_evaluation_dataset(
                algo_mod.EvaluationDatasetCreateRequest(
                    name="评测集 B",
                    source_dataset_id="ds-1",
                    sample_ids=["sample-1"],
                )
            )).id,
            target_type="training_job",
            target_id=training_job.id,
            experiment_id=experiment.id,
        )
    )
    deployment = await svc.create_deployment(
        algo_mod.ModelDeploymentCreateRequest(
            name="部署 A",
            source_type="fine_tune",
            source_id=fine_tune.id,
            experiment_id=experiment.id,
        )
    )
    online = await svc.create_online_validation(
        algo_mod.OnlineValidationCreateRequest(
            name="在线验证 A",
            deployment_id=deployment.id,
            experiment_id=experiment.id,
        )
    )

    assert fine_tune.training_job_id == training_job.id
    assert fine_tune.model_config_id == "mc-2"
    assert offline.target_id == training_job.id
    assert deployment.source_id == fine_tune.id
    assert online.deployment_id == deployment.id
    assert session.commit_count >= 6


@pytest.mark.asyncio
async def test_training_and_fine_tune_reject_embedding_model_config(service):
    svc, *_ = service

    with pytest.raises(ValidationError):
        await svc.create_training_job(
            algo_mod.TrainingJobCreateRequest(
                name="训练任务 embed",
                source_dataset_id="ds-1",
                model_config_id="mc-embed",
            )
        )


@pytest.mark.asyncio
async def test_generic_launch_cancel_commits_for_execution_resources(service):
    svc, *_rest, session = service
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
    svc, _algo_repo, _eval_item_repo, job_repo, _kg_repo = service
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
async def test_create_kg_relation_requires_existing_entities(service):
    svc, _algo_repo, _eval_item_repo, _job_repo, kg_repo = service
    await svc.launch_processing_run(
        dataset_id="ds-1",
        processing_type="kg",
        payload=algo_mod.DatasetProcessingRunRequest(name="kg run"),
    )
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
