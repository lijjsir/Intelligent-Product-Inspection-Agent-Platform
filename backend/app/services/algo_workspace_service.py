from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections import Counter
from datetime import datetime
from typing import Any

from app.core.exceptions import NotFoundError, ValidationError
from app.models.algo_resources import (
    DatasetAlignment,
    DatasetAugmentationBatch,
    DatasetExport,
    DatasetKnowledgeGraph,
    EvaluationDataset,
    Experiment,
    FineTuneRun,
    ModelDeployment,
    OfflineEvaluation,
    OnlineValidation,
    TrainingJob,
)
from app.repositories.model_config_repo import ModelConfigRepository
from app.repositories.algo_resource_repo import (
    AlgoResourceRepository,
    DatasetAlignmentPairRepository,
    DatasetAugmentationProposalRepository,
    DatasetProcessingEntityRepository,
    EvaluationDatasetItemRepository,
    PROCESSING_MODEL_MAP,
    RESOURCE_MODEL_MAP,
)
from app.repositories.dataset_repo import DatasetAsyncJobRepository, DatasetRepository, DatasetSampleRepository
from app.repositories.result_repo import ResultRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.algo_resources import (
    AlgoResourceResponse,
    DatasetAlignmentPairCreateRequest,
    DatasetAlignmentPairResponse,
    DatasetAugmentationProposalCreateRequest,
    DatasetAugmentationProposalResponse,
    DatasetExportRequest,
    DatasetKgEntityCreateRequest,
    DatasetKgEntityResponse,
    DatasetKgRelationCreateRequest,
    DatasetKgRelationResponse,
    DatasetProcessingResultsResponse,
    DatasetProcessingRunRequest,
    DatasetProcessingStatusResponse,
    EvaluationDatasetCreateRequest,
    EvaluationDatasetItemResponse,
    EvaluationDatasetSampleAppendRequest,
    EvaluationDatasetResponse,
    EvaluationDatasetUpdateRequest,
    ExperimentRelatedResourceSummary,
    ExperimentRelatedResources,
    ExperimentCreateRequest,
    ExperimentResponse,
    ExperimentUpdateRequest,
    FineTuneRunCreateRequest,
    FineTuneRunResponse,
    FineTuneRunUpdateRequest,
    ModelDeploymentCreateRequest,
    ModelDeploymentResponse,
    ModelDeploymentUpdateRequest,
    OfflineEvaluationCreateRequest,
    OfflineEvaluationResponse,
    OfflineEvaluationUpdateRequest,
    OnlineValidationCreateRequest,
    OnlineValidationResponse,
    OnlineValidationUpdateRequest,
    ResourceActionResponse,
    ResourceModelRef,
    TrainingJobCreateRequest,
    TrainingJobResponse,
    TrainingJobUpdateRequest,
)
from app.schemas.common import PagedResponse
from app.services.algo_execution_service import DeploymentManager, EvaluationEngine, ExecutionModelRef, OnlineValidationRunner, TrainingRunner
from app.services.algo_processing_service import AlgoProcessingService, ProcessingDeps
from app.services.base import TenantAwareService
from app.services.object_storage.factory import build_object_storage
from app.services.task_execution_service import has_active_celery_worker
from infra.database.session import get_session


PROCESSING_JOB_TYPE_MAP = {
    "kg": "knowledge_graph_build",
    "alignment": "alignment_run",
    "augmentation": "augmentation_run",
    "export": "dataset_export",
}

EDITABLE_STATUSES = {"draft", "failed"}
CANCELLABLE_STATUSES = {"queued", "running"}
DELETABLE_STATUSES = {"draft", "completed", "failed", "cancelled"}


def _iso_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class AlgoWorkspaceService(TenantAwareService):
    def __init__(self, session, org_id: str, user_id: str):
        super().__init__(session, org_id)
        self._user_id = user_id
        self._datasets = DatasetRepository(session)
        self._dataset_samples = DatasetSampleRepository(session)
        self._dataset_jobs = DatasetAsyncJobRepository(session)
        self._resources = AlgoResourceRepository(session)
        self._eval_items = EvaluationDatasetItemRepository(session)
        self._kg_repo = DatasetProcessingEntityRepository(session)
        self._pair_repo = DatasetAlignmentPairRepository(session)
        self._proposal_repo = DatasetAugmentationProposalRepository(session)
        self._model_configs = ModelConfigRepository(session)
        self._storage = build_object_storage()
        self._processing = AlgoProcessingService(
            ProcessingDeps(
                org_id=org_id,
                user_id=user_id,
                datasets=self._datasets,
                samples=self._dataset_samples,
                kg_repo=self._kg_repo,
                pair_repo=self._pair_repo,
                proposal_repo=self._proposal_repo,
                storage=self._storage,
            )
        )
        self._task_repo = TaskRepository(session)
        self._result_repo = ResultRepository(session)

    async def list_generic_resources(self, *, resource_type: str, page: int, size: int, keyword: str | None = None, status: str | None = None):
        model = RESOURCE_MODEL_MAP[resource_type]
        rows, total = await self._resources.list_for_owner(
            model=model,
            org_id=self._org_id,
            owner_user_id=self._user_id,
            page=page,
            size=size,
            keyword=keyword,
            status=status,
        )
        if resource_type == "evaluation_dataset":
            items = [await self._build_evaluation_dataset_response(row) for row in rows]
        else:
            items = [await self._serialize_generic_resource(resource_type, row) for row in rows]
        return {"items": items, "total": total, "page": page, "size": size}

    async def get_generic_resource(self, *, resource_type: str, resource_id: str):
        row = await self._require_generic_resource(resource_type=resource_type, resource_id=resource_id)
        if resource_type == "evaluation_dataset":
            return await self._build_evaluation_dataset_response(row)
        return await self._serialize_generic_resource(resource_type, row)

    async def create_evaluation_dataset(self, payload: EvaluationDatasetCreateRequest) -> EvaluationDatasetResponse:
        dataset = await self._require_dataset(payload.source_dataset_id)
        item_payloads = await self._resolve_eval_item_payloads(dataset_id=dataset.id, sample_ids=payload.sample_ids)
        created = await self._resources.create(
            EvaluationDataset,
            {
                "org_id": self._org_id,
                "created_by": self._user_id,
                "name": payload.name.strip(),
                "description": (payload.description or "").strip() or None,
                "status": "draft",
                "config_json": payload.config_json or {},
                "result_summary": {"source_dataset_id": dataset.id},
                "source_dataset_id": dataset.id,
            },
        )
        await self._eval_items.replace_items(
            org_id=self._org_id,
            evaluation_dataset_id=created.id,
            source_dataset_id=dataset.id,
            created_by=self._user_id,
            items=item_payloads,
        )
        await self._commit()
        return await self._build_evaluation_dataset_response(created)

    async def update_evaluation_dataset(self, resource_id: str, payload: EvaluationDatasetUpdateRequest) -> EvaluationDatasetResponse:
        row = await self._require_generic_resource(resource_type="evaluation_dataset", resource_id=resource_id)
        await self._ensure_editable(row.status)
        updates = payload.model_dump(exclude_unset=True)
        if "sample_ids" in updates:
            sample_ids = list(updates.pop("sample_ids") or [])
            existing_items = await self._eval_items.list_items_all(
                org_id=self._org_id,
                evaluation_dataset_id=row.id,
                created_by=self._user_id,
            )
            item_payloads = await self._resolve_eval_item_payloads(
                dataset_id=row.source_dataset_id,
                sample_ids=sample_ids,
                existing_items=existing_items,
            )
            await self._eval_items.replace_items(
                org_id=self._org_id,
                evaluation_dataset_id=row.id,
                source_dataset_id=row.source_dataset_id,
                created_by=self._user_id,
                items=item_payloads,
            )
        normalized = self._normalize_updates(updates)
        if normalized:
            await self._resources.save(row, normalized)
        await self._commit()
        return await self._build_evaluation_dataset_response(row)

    async def list_evaluation_dataset_items(
        self,
        *,
        resource_id: str,
        page: int,
        size: int,
        sample_type: str | None = None,
    ) -> PagedResponse[EvaluationDatasetItemResponse]:
        row = await self._require_generic_resource(resource_type="evaluation_dataset", resource_id=resource_id)
        items, total = await self._eval_items.list_items(
            org_id=self._org_id,
            evaluation_dataset_id=row.id,
            created_by=self._user_id,
            page=page,
            size=size,
            sample_type=sample_type,
        )
        return PagedResponse(
            items=await self._serialize_evaluation_dataset_items(row.source_dataset_id, items),
            total=total,
            page=page,
            size=size,
        )

    async def append_evaluation_dataset_items(self, *, resource_id: str, payload: EvaluationDatasetSampleAppendRequest) -> EvaluationDatasetResponse:
        row = await self._require_generic_resource(resource_type="evaluation_dataset", resource_id=resource_id)
        item_payloads = await self._resolve_eval_item_payloads(dataset_id=row.source_dataset_id, sample_ids=payload.sample_ids)
        existing_items = await self._eval_items.list_items_all(
            org_id=self._org_id,
            evaluation_dataset_id=row.id,
            created_by=self._user_id,
        )
        existing_sample_ids = {item.dataset_sample_id for item in existing_items if item.dataset_sample_id}
        append_items = [item for item in item_payloads if item.get("dataset_sample_id") not in existing_sample_ids]
        if append_items:
            await self._eval_items.append_items(
                org_id=self._org_id,
                evaluation_dataset_id=row.id,
                source_dataset_id=row.source_dataset_id,
                created_by=self._user_id,
                items=append_items,
            )
            await self._commit()
        return await self._build_evaluation_dataset_response(row)

    async def delete_evaluation_dataset_item(self, *, resource_id: str, item_id: str) -> None:
        row = await self._require_generic_resource(resource_type="evaluation_dataset", resource_id=resource_id)
        item = await self._eval_items.get_item(
            org_id=self._org_id,
            evaluation_dataset_id=row.id,
            item_id=item_id,
            created_by=self._user_id,
        )
        if item is None:
            raise NotFoundError("evaluation dataset item not found")
        await self._eval_items.soft_delete(item)
        await self._commit()

    async def create_training_job(self, payload: TrainingJobCreateRequest) -> TrainingJobResponse:
        await self._require_dataset_active(payload.source_dataset_id)
        await self._require_training_model_config(payload.model_config_id)
        if payload.eval_set_id:
            await self._require_generic_resource(resource_type="evaluation_dataset", resource_id=payload.eval_set_id)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        created = await self._resources.create(
            TrainingJob,
            {
                "org_id": self._org_id,
                "created_by": self._user_id,
                "name": payload.name.strip(),
                "description": (payload.description or "").strip() or None,
                "status": "draft",
                "config_json": payload.config_json or {},
                "result_summary": self._default_training_job_summary(model_config_id=payload.model_config_id),
                "source_dataset_id": payload.source_dataset_id,
                "model_config_id": payload.model_config_id,
                "eval_set_id": payload.eval_set_id,
                "experiment_id": payload.experiment_id,
                "execution_mode": None,
                "executor_job_id": None,
                "started_at": None,
                "completed_at": None,
            },
        )
        await self._commit()
        return await self._build_training_job_response(created)

    async def update_training_job(self, resource_id: str, payload: TrainingJobUpdateRequest) -> TrainingJobResponse:
        row = await self._require_generic_resource(resource_type="training_job", resource_id=resource_id)
        await self._ensure_editable(row.status)
        if payload.model_config_id:
            await self._require_training_model_config(payload.model_config_id)
        if payload.eval_set_id:
            await self._require_generic_resource(resource_type="evaluation_dataset", resource_id=payload.eval_set_id)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        updates = self._normalize_updates(payload.model_dump(exclude_unset=True))
        await self._resources.save(row, updates)
        await self._commit()
        return await self._build_training_job_response(row)

    async def launch_training_job(self, resource_id: str) -> ResourceActionResponse:
        row = await self._require_generic_resource(resource_type="training_job", resource_id=resource_id)
        if row.status not in {"draft", "failed"}:
            raise ValidationError("resource cannot be launched from current status")
        mode = await self._resolve_execution_mode()
        await self._resources.save(
            row,
            {
                "status": "queued",
                "execution_mode": mode,
                "executor_job_id": None,
                "started_at": None,
                "completed_at": None,
                "result_summary": self._default_training_job_summary(model_config_id=row.model_config_id),
            },
        )
        await self._commit()
        if mode == "celery":
            from worker.tasks.algo_workspace_task import run_resource

            run_resource.delay(
                {
                    "org_id": self._org_id,
                    "user_id": self._user_id,
                    "resource_type": "training_job",
                    "resource_id": row.id,
                    "mode": mode,
                }
            )
        else:
            asyncio.create_task(self._run_training_job(resource_id=row.id, mode=mode))
        return ResourceActionResponse(id=row.id, status="queued", execution_mode=mode, executor_job_id=None)

    async def cancel_training_job(self, resource_id: str) -> ResourceActionResponse:
        row = await self._require_generic_resource(resource_type="training_job", resource_id=resource_id)
        if row.status not in CANCELLABLE_STATUSES:
            raise ValidationError("resource cannot be cancelled from current status")
        await self._resources.save(
            row,
            {
                "status": "cancelled",
                "completed_at": datetime.utcnow(),
            },
        )
        await self._commit()
        return ResourceActionResponse(
            id=row.id,
            status="cancelled",
            execution_mode=getattr(row, "execution_mode", None),
            executor_job_id=getattr(row, "executor_job_id", None),
        )

    async def delete_training_job(self, resource_id: str) -> None:
        await self.delete_generic_resource(resource_type="training_job", resource_id=resource_id)

    async def create_fine_tune(self, payload: FineTuneRunCreateRequest) -> FineTuneRunResponse:
        training_job = await self._require_completed_resource(resource_type="training_job", resource_id=payload.training_job_id)
        self._require_deployable_artifacts(training_job.result_summary, "training job")
        await self._require_training_model_config(payload.model_config_id)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        created = await self._resources.create(
            FineTuneRun,
            {
                "org_id": self._org_id,
                "created_by": self._user_id,
                "name": payload.name.strip(),
                "description": (payload.description or "").strip() or None,
                "status": "draft",
                "config_json": payload.config_json or {},
                "result_summary": self._default_training_job_summary(model_config_id=payload.model_config_id),
                "training_job_id": payload.training_job_id,
                "model_config_id": payload.model_config_id,
                "experiment_id": payload.experiment_id,
                "execution_mode": None,
                "executor_job_id": None,
                "started_at": None,
                "completed_at": None,
            },
        )
        await self._commit()
        return await self._build_fine_tune_response(created)

    async def update_fine_tune(self, resource_id: str, payload: FineTuneRunUpdateRequest) -> FineTuneRunResponse:
        row = await self._require_generic_resource(resource_type="fine_tune", resource_id=resource_id)
        await self._ensure_editable(row.status)
        if payload.model_config_id:
            await self._require_training_model_config(payload.model_config_id)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        updates = self._normalize_updates(payload.model_dump(exclude_unset=True))
        await self._resources.save(row, updates)
        await self._commit()
        return await self._build_fine_tune_response(row)

    async def create_offline_evaluation(self, payload: OfflineEvaluationCreateRequest) -> OfflineEvaluationResponse:
        await self._require_generic_resource(resource_type="evaluation_dataset", resource_id=payload.eval_set_id)
        await self._require_completed_target_resource(payload.target_type, payload.target_id)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        created = await self._resources.create(
            OfflineEvaluation,
            {
                "org_id": self._org_id,
                "created_by": self._user_id,
                "name": payload.name.strip(),
                "description": (payload.description or "").strip() or None,
                "status": "draft",
                "config_json": payload.config_json or {},
                "result_summary": self._default_offline_evaluation_summary(),
                "eval_set_id": payload.eval_set_id,
                "target_type": payload.target_type,
                "target_id": payload.target_id,
                "experiment_id": payload.experiment_id,
                "execution_mode": None,
                "executor_job_id": None,
                "started_at": None,
                "completed_at": None,
            },
        )
        await self._commit()
        return OfflineEvaluationResponse.model_validate(created)

    async def update_offline_evaluation(self, resource_id: str, payload: OfflineEvaluationUpdateRequest) -> OfflineEvaluationResponse:
        row = await self._require_generic_resource(resource_type="offline_evaluation", resource_id=resource_id)
        await self._ensure_editable(row.status)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        updates = self._normalize_updates(payload.model_dump(exclude_unset=True))
        await self._resources.save(row, updates)
        await self._commit()
        return OfflineEvaluationResponse.model_validate(row)

    async def create_online_validation(self, payload: OnlineValidationCreateRequest) -> OnlineValidationResponse:
        await self._require_completed_resource(resource_type="deployment", resource_id=payload.deployment_id)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        deployment = await self._require_generic_resource(resource_type="deployment", resource_id=payload.deployment_id)
        runtime_registration = (getattr(deployment, "result_summary", {}) or {}).get("runtime_registration") or {}
        if not runtime_registration:
            raise ValidationError("deployment is missing runtime_registration")
        created = await self._resources.create(
            OnlineValidation,
            {
                "org_id": self._org_id,
                "created_by": self._user_id,
                "name": payload.name.strip(),
                "description": (payload.description or "").strip() or None,
                "status": "draft",
                "config_json": payload.config_json or {},
                "result_summary": {
                    "summary": {
                        "status": "draft",
                        "execution_mode": None,
                        "started_at": None,
                        "completed_at": None,
                        "deployment_id": payload.deployment_id,
                        "validation_type": "shadow",
                        "replay_source": "historical_tasks",
                        "replay_count": 0,
                    },
                    "metrics": {},
                    "replay_samples": [],
                    "artifacts": [],
                    "logs": [],
                },
                "deployment_id": payload.deployment_id,
                "experiment_id": payload.experiment_id,
                "execution_mode": None,
                "executor_job_id": None,
                "started_at": None,
                "completed_at": None,
            },
        )
        await self._commit()
        return OnlineValidationResponse.model_validate(created)

    async def update_online_validation(self, resource_id: str, payload: OnlineValidationUpdateRequest) -> OnlineValidationResponse:
        row = await self._require_generic_resource(resource_type="online_validation", resource_id=resource_id)
        await self._ensure_editable(row.status)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        updates = self._normalize_updates(payload.model_dump(exclude_unset=True))
        await self._resources.save(row, updates)
        await self._commit()
        return OnlineValidationResponse.model_validate(row)

    async def create_experiment(self, payload: ExperimentCreateRequest) -> ExperimentResponse:
        created = await self._resources.create(
            Experiment,
            {
                "org_id": self._org_id,
                "created_by": self._user_id,
                "name": payload.name.strip(),
                "description": (payload.description or "").strip() or None,
                "status": "draft",
                "config_json": payload.config_json or {},
                "result_summary": {"artifacts": [], "metrics": {}, "logs": []},
            },
        )
        await self._commit()
        return await self._build_experiment_response(created)

    async def update_experiment(self, resource_id: str, payload: ExperimentUpdateRequest) -> ExperimentResponse:
        row = await self._require_generic_resource(resource_type="experiment", resource_id=resource_id)
        await self._ensure_editable(row.status)
        updates = self._normalize_updates(payload.model_dump(exclude_unset=True))
        await self._resources.save(row, updates)
        await self._commit()
        return await self._build_experiment_response(row)

    async def create_deployment(self, payload: ModelDeploymentCreateRequest) -> ModelDeploymentResponse:
        if payload.source_type not in {"training_job", "fine_tune"}:
            raise ValidationError("deployment source_type must be training_job or fine_tune")
        source = await self._require_completed_target_resource(payload.source_type, payload.source_id)
        self._require_deployable_artifacts(source.result_summary, payload.source_type)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        created = await self._resources.create(
            ModelDeployment,
            {
                "org_id": self._org_id,
                "created_by": self._user_id,
                "name": payload.name.strip(),
                "description": (payload.description or "").strip() or None,
                "status": "draft",
                "config_json": payload.config_json or {},
                "result_summary": self._default_deployment_summary(),
                "source_type": payload.source_type,
                "source_id": payload.source_id,
                "experiment_id": payload.experiment_id,
                "execution_mode": None,
                "executor_job_id": None,
                "started_at": None,
                "completed_at": None,
            },
        )
        await self._commit()
        return ModelDeploymentResponse.model_validate(created)

    async def update_deployment(self, resource_id: str, payload: ModelDeploymentUpdateRequest) -> ModelDeploymentResponse:
        row = await self._require_generic_resource(resource_type="deployment", resource_id=resource_id)
        await self._ensure_editable(row.status)
        if payload.experiment_id:
            await self._require_generic_resource(resource_type="experiment", resource_id=payload.experiment_id)
        updates = self._normalize_updates(payload.model_dump(exclude_unset=True))
        await self._resources.save(row, updates)
        await self._commit()
        return ModelDeploymentResponse.model_validate(row)

    async def delete_generic_resource(self, *, resource_type: str, resource_id: str) -> None:
        row = await self._require_generic_resource(resource_type=resource_type, resource_id=resource_id)
        if getattr(row, "status", "draft") not in DELETABLE_STATUSES:
            raise ValidationError("resource cannot be deleted from current status")
        if resource_type == "evaluation_dataset":
            await self._eval_items.soft_delete_many(
                org_id=self._org_id,
                evaluation_dataset_id=row.id,
                created_by=self._user_id,
            )
        await self._resources.soft_delete(row)
        await self._commit()

    async def launch_generic_resource(self, *, resource_type: str, resource_id: str) -> ResourceActionResponse:
        row = await self._require_generic_resource(resource_type=resource_type, resource_id=resource_id)
        if row.status not in {"draft", "failed", "cancelled"}:
            raise ValidationError("resource cannot be launched from current status")
        mode = await self._resolve_execution_mode()
        await self._resources.save(
            row,
            {
                "status": "queued",
                "execution_mode": mode,
                "executor_job_id": None,
                "started_at": None,
                "completed_at": None,
                "result_summary": self._default_generic_execution_summary(resource_type),
            },
        )
        await self._commit()
        if resource_type == "fine_tune":
            if mode == "celery":
                from worker.tasks.algo_workspace_task import run_resource

                run_resource.delay(
                    {
                        "org_id": self._org_id,
                        "user_id": self._user_id,
                        "resource_type": "fine_tune",
                        "resource_id": row.id,
                        "mode": mode,
                    }
                )
            else:
                asyncio.create_task(self._run_fine_tune_job(resource_id=row.id, mode=mode))
        elif resource_type == "offline_evaluation":
            if mode == "celery":
                from worker.tasks.algo_workspace_task import run_resource

                run_resource.delay(
                    {
                        "org_id": self._org_id,
                        "user_id": self._user_id,
                        "resource_type": "offline_evaluation",
                        "resource_id": row.id,
                        "mode": mode,
                    }
                )
            else:
                asyncio.create_task(self._run_offline_evaluation_job(resource_id=row.id, mode=mode))
        elif resource_type == "deployment":
            if mode == "celery":
                from worker.tasks.algo_workspace_task import run_resource

                run_resource.delay(
                    {
                        "org_id": self._org_id,
                        "user_id": self._user_id,
                        "resource_type": "deployment",
                        "resource_id": row.id,
                        "mode": mode,
                    }
                )
            else:
                asyncio.create_task(self._run_deployment_job(resource_id=row.id, mode=mode))
        elif resource_type == "online_validation":
            if mode == "celery":
                from worker.tasks.algo_workspace_task import run_resource

                run_resource.delay(
                    {
                        "org_id": self._org_id,
                        "user_id": self._user_id,
                        "resource_type": "online_validation",
                        "resource_id": row.id,
                        "mode": mode,
                    }
                )
            else:
                asyncio.create_task(self._run_online_validation_job(resource_id=row.id, mode=mode))
        else:
            asyncio.create_task(self._run_generic_resource(resource_type=resource_type, resource_id=row.id, mode=mode))
        return ResourceActionResponse(id=row.id, status="queued", execution_mode=mode, executor_job_id=None)

    async def cancel_generic_resource(self, *, resource_type: str, resource_id: str) -> ResourceActionResponse:
        row = await self._require_generic_resource(resource_type=resource_type, resource_id=resource_id)
        if row.status not in CANCELLABLE_STATUSES:
            raise ValidationError("resource cannot be cancelled from current status")
        await self._resources.save(
            row,
            {
                "status": "cancelled",
                "completed_at": datetime.utcnow(),
            },
        )
        await self._commit()
        return ResourceActionResponse(
            id=row.id,
            status="cancelled",
            execution_mode=getattr(row, "execution_mode", None),
            executor_job_id=getattr(row, "executor_job_id", None),
        )

    async def launch_processing_run(self, *, dataset_id: str, processing_type: str, payload: DatasetProcessingRunRequest) -> DatasetProcessingStatusResponse:
        await self._require_dataset(dataset_id)
        model = PROCESSING_MODEL_MAP[processing_type]
        existing_rows, _ = await self._resources.list_for_owner(
            model=model,
            org_id=self._org_id,
            owner_user_id=self._user_id,
            page=1,
            size=1,
            extra_filters=[model.dataset_id == dataset_id],
        )
        if existing_rows:
            row = existing_rows[0]
            if row.status in {"queued", "running"}:
                raise ValidationError("processing run already active")
            await self._resources.save(
                row,
                {
                    "name": payload.name.strip(),
                    "description": (payload.description or "").strip() or None,
                    "config_json": payload.config_json or {},
                    "status": "queued",
                    "result_summary": self._default_processing_summary(processing_type),
                },
            )
        else:
            row = await self._resources.create(
                model,
                {
                    "org_id": self._org_id,
                    "created_by": self._user_id,
                    "dataset_id": dataset_id,
                    "name": payload.name.strip(),
                    "description": (payload.description or "").strip() or None,
                    "status": "queued",
                    "config_json": payload.config_json or {},
                    "result_summary": self._default_processing_summary(processing_type),
                },
            )

        mode = await self._resolve_execution_mode()
        job = await self._dataset_jobs.create(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "created_by": self._user_id,
                "job_type": PROCESSING_JOB_TYPE_MAP[processing_type],
                "status": "queued",
                "payload_json": {"resource_id": row.id, "processing_type": processing_type},
                "result_summary": self._default_processing_summary(processing_type),
            }
        )
        await self._commit()
        if mode == "celery":
            from worker.tasks.algo_workspace_task import run_processing

            run_processing.delay(
                {
                    "org_id": self._org_id,
                    "user_id": self._user_id,
                    "dataset_id": dataset_id,
                    "processing_type": processing_type,
                    "resource_id": row.id,
                    "job_id": job.id,
                    "mode": mode,
                }
            )
        else:
            asyncio.create_task(self._run_processing(processing_type=processing_type, dataset_id=dataset_id, resource_id=row.id, job_id=job.id, mode=mode))
        return await self.get_processing_status(dataset_id=dataset_id, processing_type=processing_type)

    async def get_processing_status(self, *, dataset_id: str, processing_type: str) -> DatasetProcessingStatusResponse:
        await self._require_dataset(dataset_id)
        model = PROCESSING_MODEL_MAP[processing_type]
        rows, _ = await self._resources.list_for_owner(
            model=model,
            org_id=self._org_id,
            owner_user_id=self._user_id,
            page=1,
            size=1,
            extra_filters=[model.dataset_id == dataset_id],
        )
        resource = rows[0] if rows else None
        jobs = await self._dataset_jobs.list_recent_for_dataset(
            org_id=self._org_id,
            dataset_id=dataset_id,
            owner_user_id=self._user_id,
            limit=20,
        )
        job_type = PROCESSING_JOB_TYPE_MAP[processing_type]
        latest_job = next((job for job in jobs if job.job_type == job_type and job.deleted_at is None), None)
        summary = dict((resource.result_summary if resource else {}) or self._default_processing_summary(processing_type))
        phases = list(summary.get("phases") or self._default_phases(processing_type))
        warnings = list(summary.get("warnings") or [])
        return DatasetProcessingStatusResponse(
            resource=AlgoResourceResponse.model_validate(resource) if resource else None,
            latest_job={
                "id": latest_job.id,
                "status": latest_job.status,
                "job_type": latest_job.job_type,
                "result_summary": latest_job.result_summary,
                "created_at": latest_job.created_at.isoformat() if latest_job and latest_job.created_at else None,
            } if latest_job else None,
            summary=summary,
            phases=phases,
            progress=int(summary.get("progress") or (100 if resource and resource.status == "completed" else 0)),
            warnings=warnings,
        )

    async def get_processing_results(
        self,
        *,
        dataset_id: str,
        processing_type: str,
        entity_type: str | None = None,
        keyword: str | None = None,
        min_score: float | None = None,
        only_confirmed: bool | None = None,
        sample_id: str | None = None,
    ) -> DatasetProcessingResultsResponse:
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type=processing_type)
        summary = dict(resource.result_summary or self._default_processing_summary(processing_type))
        if processing_type == "kg":
            entities = await self._kg_repo.list_entities(org_id=self._org_id, knowledge_graph_id=resource.id, created_by=self._user_id)
            relations = await self._kg_repo.list_relations(org_id=self._org_id, knowledge_graph_id=resource.id, created_by=self._user_id)
            if entity_type:
                entities = [row for row in entities if str(row.entity_type) == entity_type]
            if keyword:
                needle = keyword.strip().lower()
                entities = [row for row in entities if needle in str(row.name or "").lower() or needle in str(row.description or "").lower()]
                relations = [
                    row
                    for row in relations
                    if needle in str(row.relation_type or "").lower()
                    or needle in str((row.properties_json or {}).get("source_text") or "").lower()
                ]
            return DatasetProcessingResultsResponse(
                summary=summary,
                entities=[DatasetKgEntityResponse.model_validate(row) for row in entities],
                relations=[DatasetKgRelationResponse.model_validate(row) for row in relations],
            )
        if processing_type == "alignment":
            pairs = await self._pair_repo.list_pairs_filtered(
                org_id=self._org_id,
                alignment_id=resource.id,
                created_by=self._user_id,
                min_score=min_score,
                only_confirmed=only_confirmed,
                sample_id=sample_id,
            )
            return DatasetProcessingResultsResponse(
                summary=summary,
                pairs=[DatasetAlignmentPairResponse.model_validate(row) for row in pairs],
            )
        if processing_type == "augmentation":
            proposals = await self._proposal_repo.list_proposals(org_id=self._org_id, batch_id=resource.id, created_by=self._user_id)
            return DatasetProcessingResultsResponse(
                summary=summary,
                proposals=[DatasetAugmentationProposalResponse.model_validate(row) for row in proposals],
            )
        return DatasetProcessingResultsResponse(
            summary=summary,
            artifact=dict(summary.get("artifact") or {}),
        )

    async def get_processing_subgraph(self, *, dataset_id: str, entity_type: str | None = None, keyword: str | None = None) -> dict[str, Any]:
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="kg")
        entities = await self._kg_repo.list_entities(org_id=self._org_id, knowledge_graph_id=resource.id, created_by=self._user_id)
        relations = await self._kg_repo.list_relations(org_id=self._org_id, knowledge_graph_id=resource.id, created_by=self._user_id)
        if entity_type:
            entities = [row for row in entities if str(row.entity_type) == entity_type]
        if keyword:
            needle = keyword.strip().lower()
            entities = [row for row in entities if needle in str(row.name or "").lower() or needle in str(row.description or "").lower()]
            filtered_ids = {row.id for row in entities}
            relations = [row for row in relations if row.source_entity_id in filtered_ids or row.target_entity_id in filtered_ids]
        nodes = [
            {
                "id": row.id,
                "name": row.name,
                "entity_type": row.entity_type,
                "value": float(row.confidence or 1.0),
                "description": row.description,
                "properties_json": row.properties_json or {},
            }
            for row in entities
        ]
        edges = [
            {
                "id": row.id,
                "source": row.source_entity_id,
                "target": row.target_entity_id,
                "relation_type": row.relation_type,
                "value": float(row.confidence or 1.0),
                "properties_json": row.properties_json or {},
            }
            for row in relations
        ]
        stats = {
            "entity_count": len(nodes),
            "relation_count": len(edges),
            "entity_types": dict(Counter(node["entity_type"] for node in nodes)),
        }
        return {"nodes": nodes, "edges": edges, "stats": stats}

    async def create_kg_entity(self, *, dataset_id: str, payload: DatasetKgEntityCreateRequest) -> DatasetKgEntityResponse:
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="kg")
        self._ensure_processing_resource_editable(resource)
        created = await self._kg_repo.create_entity(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "knowledge_graph_id": resource.id,
                "created_by": self._user_id,
                "name": payload.name.strip(),
                "entity_type": payload.entity_type.strip(),
                "description": (payload.description or "").strip() or None,
                "properties_json": {"source": "manual", **(payload.properties_json or {})},
                "confidence": payload.confidence,
            }
        )
        return DatasetKgEntityResponse.model_validate(created)

    async def delete_kg_entity(self, *, entity_id: str) -> None:
        entity = await self._kg_repo.get_entity(org_id=self._org_id, entity_id=entity_id, created_by=self._user_id)
        if entity is None:
            raise NotFoundError("knowledge graph entity not found")
        resource = await self._require_processing_resource(dataset_id=entity.dataset_id, processing_type="kg")
        self._ensure_processing_resource_editable(resource)
        await self._kg_repo.delete_entity(entity)

    async def create_kg_relation(self, *, dataset_id: str, payload: DatasetKgRelationCreateRequest) -> DatasetKgRelationResponse:
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="kg")
        self._ensure_processing_resource_editable(resource)
        await self._require_kg_entity(payload.source_entity_id)
        await self._require_kg_entity(payload.target_entity_id)
        created = await self._kg_repo.create_relation(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "knowledge_graph_id": resource.id,
                "created_by": self._user_id,
                "source_entity_id": payload.source_entity_id,
                "target_entity_id": payload.target_entity_id,
                "relation_type": payload.relation_type.strip(),
                "properties_json": {"source": "manual", **(payload.properties_json or {})},
                "confidence": payload.confidence,
            }
        )
        return DatasetKgRelationResponse.model_validate(created)

    async def delete_kg_relation(self, *, relation_id: str) -> None:
        relation = await self._kg_repo.get_relation(org_id=self._org_id, relation_id=relation_id, created_by=self._user_id)
        if relation is None:
            raise NotFoundError("knowledge graph relation not found")
        resource = await self._require_processing_resource(dataset_id=relation.dataset_id, processing_type="kg")
        self._ensure_processing_resource_editable(resource)
        await self._kg_repo.delete_relation(relation)

    async def create_alignment_pair(self, *, dataset_id: str, payload: DatasetAlignmentPairCreateRequest) -> DatasetAlignmentPairResponse:
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="alignment")
        self._ensure_processing_resource_editable(resource)
        if payload.source_sample_id:
            await self._require_dataset_sample(dataset_id=dataset_id, sample_id=payload.source_sample_id, sample_type="image")
        if payload.target_sample_id:
            await self._require_dataset_sample(dataset_id=dataset_id, sample_id=payload.target_sample_id, sample_type="text")
        created = await self._pair_repo.create_pair(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "alignment_id": resource.id,
                "created_by": self._user_id,
                "source_sample_id": payload.source_sample_id,
                "target_sample_id": payload.target_sample_id,
                "relation_type": payload.relation_type.strip(),
                "similarity_score": payload.similarity_score,
                "payload_json": {**(payload.payload_json or {}), "source": "manual"},
                "confirmation_status": "confirmed",
            }
        )
        return DatasetAlignmentPairResponse.model_validate(created)

    async def confirm_alignment_pair(self, *, dataset_id: str, pair_id: str) -> DatasetAlignmentPairResponse:
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="alignment")
        pair = await self._pair_repo.get_pair(org_id=self._org_id, pair_id=pair_id, created_by=self._user_id)
        if pair is None or pair.alignment_id != resource.id:
            raise NotFoundError("alignment pair not found")
        await self._pair_repo.update_pair(pair, {"confirmation_status": "confirmed"})
        return DatasetAlignmentPairResponse.model_validate(pair)

    async def delete_alignment_pair(self, *, pair_id: str) -> None:
        pair = await self._pair_repo.get_pair(org_id=self._org_id, pair_id=pair_id, created_by=self._user_id)
        if pair is None:
            raise NotFoundError("alignment pair not found")
        resource = await self._require_processing_resource(dataset_id=pair.dataset_id, processing_type="alignment")
        self._ensure_processing_resource_editable(resource)
        await self._pair_repo.delete_pair(pair)

    async def create_augmentation_proposal(self, *, dataset_id: str, payload: DatasetAugmentationProposalCreateRequest) -> DatasetAugmentationProposalResponse:
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="augmentation")
        self._ensure_processing_resource_editable(resource)
        created = await self._proposal_repo.create_proposal(
            {
                "org_id": self._org_id,
                "dataset_id": dataset_id,
                "batch_id": resource.id,
                "created_by": self._user_id,
                "name": payload.name.strip(),
                "description": (payload.description or "").strip() or None,
                "status": "draft",
                "config_json": payload.config_json or {},
                "result_summary": payload.result_summary or {},
                "source_sample_id": payload.source_sample_id,
                "augmentation_method": payload.augmentation_method,
                "augmentation_params": payload.augmentation_params or {},
            }
        )
        return DatasetAugmentationProposalResponse.model_validate(created)

    async def delete_augmentation_proposal(self, *, proposal_id: str) -> None:
        proposal = await self._proposal_repo.get_proposal(org_id=self._org_id, proposal_id=proposal_id, created_by=self._user_id)
        if proposal is None:
            raise NotFoundError("augmentation proposal not found")
        resource = await self._require_processing_resource(dataset_id=proposal.dataset_id, processing_type="augmentation")
        self._ensure_processing_resource_editable(resource)
        await self._proposal_repo.delete_proposal(proposal)

    async def create_export(self, *, dataset_id: str, payload: DatasetExportRequest) -> AlgoResourceResponse:
        await self.launch_processing_run(dataset_id=dataset_id, processing_type="export", payload=DatasetProcessingRunRequest(name=payload.name, description=payload.description, config_json=payload.model_dump()))
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="export")
        return AlgoResourceResponse.model_validate(resource)

    async def apply_augmentation(self, *, dataset_id: str, proposal_ids: list[str]) -> dict[str, Any]:
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="augmentation")
        if not proposal_ids:
            raise ValidationError("proposal_ids cannot be empty")
        proposals = await self._proposal_repo.list_proposals(org_id=self._org_id, batch_id=resource.id, created_by=self._user_id)
        proposal_map = {row.id: row for row in proposals}
        created_ids: list[str] = []
        history_entries: list[dict[str, Any]] = []
        for proposal_id in proposal_ids:
            proposal = proposal_map.get(proposal_id)
            if proposal is None:
                raise NotFoundError("augmentation proposal not found")
            if proposal.status == "completed":
                continue
            source_sample_id = proposal.source_sample_id
            source = None
            if source_sample_id:
                source = await self._dataset_samples.get(
                    org_id=self._org_id,
                    dataset_id=dataset_id,
                    sample_id=source_sample_id,
                    owner_user_id=self._user_id,
                )
            text_content = (source.text_content if source and source.text_content else proposal.description or proposal.name or "").strip()
            if not text_content:
                continue
            created = await self._dataset_samples.create(
                {
                    "org_id": self._org_id,
                    "dataset_id": dataset_id,
                    "created_by": self._user_id,
                    "sample_type": "text",
                    "sample_name": f"aug-{proposal.name}",
                    "text_content": text_content,
                    "content_type": "text/plain",
                    "size_bytes": len(text_content.encode("utf-8")),
                    "checksum_sha256": hashlib.sha256(text_content.encode("utf-8")).hexdigest(),
                "annotation_data": {"augmentation": proposal.name},
                "quality_score": None,
                "related_entities": [],
                "source_metadata": {
                    "source_sample_id": source_sample_id,
                    "augmentation_proposal_id": proposal.id,
                    "augmentation_preview": text_content[:200],
                },
                "preview_text": text_content[:200],
                "is_augmented": True,
                "augmentation_source_id": source_sample_id,
                "augmentation_method": proposal.augmentation_method or "entity_substitution",
                "augmentation_params": proposal.augmentation_params or proposal.config_json or {},
            }
            )
            created_ids.append(created.id)
            history_entries.append(
                {
                    "proposal_id": proposal.id,
                    "proposal_name": proposal.name,
                    "created_sample_id": created.id,
                    "source_sample_id": source_sample_id,
                    "augmentation_method": proposal.augmentation_method or "entity_substitution",
                }
            )
            await self._proposal_repo.update_proposal(proposal, {"status": "completed", "result_summary": {**dict(proposal.result_summary or {}), "created_sample_id": created.id, "created_sample_ids": [created.id]}})
        if created_ids:
            dataset = await self._require_dataset(dataset_id)
            await self._datasets.recalculate_counters(dataset_id=dataset.id)
        if created_ids:
            batch = await self._resources.get(model=DatasetAugmentationBatch, org_id=self._org_id, resource_id=resource.id, owner_user_id=self._user_id)
            if batch is not None:
                history = list(dict(batch.history_json or {}).get("history") or [])
                history.extend(history_entries)
                await self._resources.save(batch, {"history_json": {"history": history}})
        return {"created_sample_ids": created_ids, "proposal_ids": proposal_ids, "history": history_entries}

    async def get_augmentation_history(self, *, dataset_id: str) -> dict[str, Any]:
        resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="augmentation")
        history = await self._proposal_repo.list_history(org_id=self._org_id, dataset_id=dataset_id, created_by=self._user_id)
        return {
            "batch_id": resource.id,
            "history": [
                {
                    **DatasetAugmentationProposalResponse.model_validate(row).model_dump(),
                    "created_sample_id": (dict(getattr(row, "result_summary", None) or {}).get("created_sample_id")),
                    "created_sample_ids": list(dict(getattr(row, "result_summary", None) or {}).get("created_sample_ids") or []),
                }
                for row in history
            ],
        }

    async def _run_kg_build(self, *, dataset_id: str, resource) -> dict[str, Any]:
        return await self._processing.run_kg_build(dataset_id=dataset_id, resource_id=resource.id, config_json=resource.config_json)

    async def _run_alignment_build(self, *, dataset_id: str, resource) -> dict[str, Any]:
        model = await self._get_active_embedding_model(resource.config_json)
        return await self._processing.run_alignment_build(
            dataset_id=dataset_id,
            resource_id=resource.id,
            config_json=resource.config_json,
            embedding_model=model,
        )

    async def _run_augmentation_build(self, *, dataset_id: str, resource) -> dict[str, Any]:
        return await self._processing.run_augmentation_build(dataset_id=dataset_id, resource_id=resource.id)

    async def _run_export_build(self, *, dataset_id: str, resource) -> dict[str, Any]:
        dataset = await self._require_dataset(dataset_id)
        alignment_resource_id: str | None = None
        try:
            alignment_resource = await self._require_processing_resource(dataset_id=dataset_id, processing_type="alignment")
            alignment_resource_id = alignment_resource.id
        except NotFoundError:
            alignment_resource_id = None
        try:
            return await self._processing.run_export_build(
                dataset_id=dataset_id,
                resource_id=resource.id,
                dataset=dataset,
                config_json=resource.config_json,
                alignment_resource_id=alignment_resource_id,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    async def _run_processing(self, *, processing_type: str, dataset_id: str, resource_id: str, job_id: str, mode: str) -> None:
        await asyncio.sleep(0)
        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            resource = await service._require_processing_resource(dataset_id=dataset_id, processing_type=processing_type)
            await service._resources.save(resource, {"status": "running", "result_summary": {**dict(resource.result_summary or {}), "progress": 5, "warnings": [], "phases": service._default_phases(processing_type)}})
            tracked_job = await service._dataset_jobs.get(
                org_id=self._org_id,
                dataset_id=dataset_id,
                job_id=job_id,
                owner_user_id=self._user_id,
            )
            if tracked_job is not None:
                tracked_job.status = "running"
                tracked_job.result_summary = {"mode": mode, "status": "running"}
            await session.commit()
        await asyncio.sleep(0.05)

        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            resource = await service._require_processing_resource(dataset_id=dataset_id, processing_type=processing_type)
            if processing_type == "kg":
                summary = await service._run_kg_build(dataset_id=dataset_id, resource=resource)
            elif processing_type == "alignment":
                summary = await service._run_alignment_build(dataset_id=dataset_id, resource=resource)
            elif processing_type == "augmentation":
                summary = await service._run_augmentation_build(dataset_id=dataset_id, resource=resource)
            else:
                summary = await service._run_export_build(dataset_id=dataset_id, resource=resource)
            await service._resources.save(resource, {"status": "completed", "result_summary": summary})
            tracked_job = await service._dataset_jobs.get(
                org_id=self._org_id,
                dataset_id=dataset_id,
                job_id=job_id,
                owner_user_id=self._user_id,
            )
            if tracked_job is not None:
                tracked_job.status = "completed"
                tracked_job.result_summary = summary
            dataset = await service._require_dataset(dataset_id)
            if processing_type == "kg":
                dataset.knowledge_graph_status = "completed"
            elif processing_type == "alignment":
                dataset.alignment_status = "completed"
            elif processing_type == "augmentation":
                dataset.augmentation_status = "completed"
            await session.commit()

    async def _run_generic_resource(self, *, resource_type: str, resource_id: str, mode: str) -> None:
        await asyncio.sleep(0)
        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type=resource_type, resource_id=resource_id)
            await service._resources.save(
                row,
                {
                    "status": "running",
                    "execution_mode": mode,
                    "started_at": datetime.utcnow(),
                },
            )
            await session.commit()

        await asyncio.sleep(0.05)

        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type=resource_type, resource_id=resource_id)
            await service._resources.save(
                row,
                {
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                    "result_summary": service._default_generic_completion_summary(resource_type, row.result_summary),
                },
            )
            await session.commit()

    async def _run_training_job(self, *, resource_id: str, mode: str) -> None:
        await asyncio.sleep(0)
        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="training_job", resource_id=resource_id)
            if row.status == "cancelled":
                return
            started_at = datetime.utcnow()
            await service._resources.save(
                row,
                {
                    "status": "running",
                    "started_at": started_at,
                    "result_summary": service._default_training_job_summary(
                        status="running",
                        execution_mode=mode,
                        started_at=started_at,
                        model_config_id=row.model_config_id,
                    ),
                },
            )
            await session.commit()

        await asyncio.sleep(0.05)

        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="training_job", resource_id=resource_id)
            if row.status == "cancelled":
                return
            completed_at = datetime.utcnow()
            model = await service._model_configs.get(service._org_id, row.model_config_id)
            model_ref = service._to_execution_model_ref(model)
            await service._resources.save(
                row,
                {
                    "status": "completed",
                    "completed_at": completed_at,
                    "result_summary": TrainingRunner.run_training(
                        resource_id=row.id,
                        resource_name=row.name,
                        source_dataset_id=row.source_dataset_id,
                        model_ref=model_ref,
                        config_json=row.config_json,
                        execution_mode=mode,
                        started_at=getattr(row, "started_at", None),
                        completed_at=completed_at,
                    ),
                },
            )
            await session.commit()

    async def _run_fine_tune_job(self, *, resource_id: str, mode: str) -> None:
        await asyncio.sleep(0)
        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="fine_tune", resource_id=resource_id)
            if row.status == "cancelled":
                return
            started_at = datetime.utcnow()
            await service._resources.save(
                row,
                {
                    "status": "running",
                    "started_at": started_at,
                    "result_summary": service._default_training_job_summary(
                        status="running",
                        execution_mode=mode,
                        started_at=started_at,
                        model_config_id=row.model_config_id,
                    ),
                },
            )
            await session.commit()

        await asyncio.sleep(0.05)

        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="fine_tune", resource_id=resource_id)
            if row.status == "cancelled":
                return
            training_job = await service._require_generic_resource(resource_type="training_job", resource_id=row.training_job_id)
            model = await service._model_configs.get(service._org_id, row.model_config_id)
            model_ref = service._to_execution_model_ref(model)
            completed_at = datetime.utcnow()
            await service._resources.save(
                row,
                {
                    "status": "completed",
                    "completed_at": completed_at,
                    "result_summary": TrainingRunner.run_fine_tune(
                        resource_id=row.id,
                        resource_name=row.name,
                        training_job_id=row.training_job_id,
                        base_training_summary=training_job.result_summary,
                        model_ref=model_ref,
                        config_json=row.config_json,
                        execution_mode=mode,
                        started_at=getattr(row, "started_at", None),
                        completed_at=completed_at,
                    ),
                },
            )
            await session.commit()

    async def _run_offline_evaluation_job(self, *, resource_id: str, mode: str) -> None:
        await asyncio.sleep(0)
        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="offline_evaluation", resource_id=resource_id)
            if row.status == "cancelled":
                return
            started_at = datetime.utcnow()
            await service._resources.save(
                row,
                {
                    "status": "running",
                    "started_at": started_at,
                    "result_summary": service._default_offline_evaluation_summary(
                        status="running",
                        execution_mode=mode,
                        started_at=started_at,
                    ),
                },
            )
            await session.commit()

        await asyncio.sleep(0.05)

        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="offline_evaluation", resource_id=resource_id)
            if row.status == "cancelled":
                return
            eval_set = await service._require_generic_resource(resource_type="evaluation_dataset", resource_id=row.eval_set_id)
            sample_count = await service._eval_items.count_items(
                org_id=service._org_id,
                evaluation_dataset_id=eval_set.id,
                created_by=service._user_id,
            )
            target = await service._require_completed_target_resource(row.target_type, row.target_id)
            completed_at = datetime.utcnow()
            await service._resources.save(
                row,
                {
                    "status": "completed",
                    "completed_at": completed_at,
                    "result_summary": EvaluationEngine.run_offline_evaluation(
                        resource_id=row.id,
                        resource_name=row.name,
                        eval_set_id=row.eval_set_id,
                        sample_count=sample_count,
                        target_type=row.target_type,
                        target_id=row.target_id,
                        target_summary=target.result_summary,
                        config_json=row.config_json,
                        execution_mode=mode,
                        started_at=getattr(row, "started_at", None),
                        completed_at=completed_at,
                    ),
                },
            )
            await session.commit()

    async def _run_deployment_job(self, *, resource_id: str, mode: str) -> None:
        await asyncio.sleep(0)
        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="deployment", resource_id=resource_id)
            if row.status == "cancelled":
                return
            started_at = datetime.utcnow()
            await service._resources.save(
                row,
                {
                    "status": "running",
                    "started_at": started_at,
                    "result_summary": service._default_deployment_summary(
                        status="running",
                        execution_mode=mode,
                        started_at=started_at,
                    ),
                },
            )
            await session.commit()

    async def _run_online_validation_job(self, *, resource_id: str, mode: str) -> None:
        await asyncio.sleep(0)
        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="online_validation", resource_id=resource_id)
            if row.status == "cancelled":
                return
            started_at = datetime.utcnow()
            await service._resources.save(
                row,
                {
                    "status": "running",
                    "started_at": started_at,
                    "result_summary": {
                        "summary": {
                            "status": "running",
                            "execution_mode": mode,
                            "started_at": _iso_dt(started_at),
                            "completed_at": None,
                            "deployment_id": row.deployment_id,
                            "validation_type": "shadow",
                        },
                        "metrics": {},
                        "replay_samples": [],
                        "artifacts": [],
                        "logs": [],
                    },
                },
            )
            await session.commit()

        await asyncio.sleep(0.05)

        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="online_validation", resource_id=resource_id)
            if row.status == "cancelled":
                return
            deployment = await service._require_completed_target_resource("deployment", row.deployment_id)
            task_ids = await service._select_validation_replay_task_ids(limit=5)
            replay_tasks = await service._build_validation_replay_tasks(task_ids)
            completed_at = datetime.utcnow()
            await service._resources.save(
                row,
                {
                    "status": "completed",
                    "completed_at": completed_at,
                    "result_summary": OnlineValidationRunner.run_shadow_validation(
                        resource_id=row.id,
                        resource_name=row.name,
                        deployment_id=row.deployment_id,
                        deployment_summary=deployment.result_summary,
                        replay_tasks=replay_tasks,
                        config_json=row.config_json,
                        execution_mode=mode,
                        started_at=getattr(row, "started_at", None),
                        completed_at=completed_at,
                    ),
                },
            )
            await session.commit()

        await asyncio.sleep(0.05)

        async with get_session() as session:
            service = AlgoWorkspaceService(session, self._org_id, self._user_id)
            row = await service._require_generic_resource(resource_type="online_validation", resource_id=resource_id)
            if row.status == "cancelled":
                return
            completed_at = datetime.utcnow()
            previous_summary = dict(row.result_summary or {})
            summary = dict(previous_summary.get("summary") or {})
            summary.update(
                {
                    "status": "completed",
                    "completed_at": _iso_dt(completed_at),
                    "deployment_id": row.deployment_id,
                    "execution_mode": mode,
                    "validation_type": summary.get("validation_type") or "shadow",
                }
            )
            await service._resources.save(
                row,
                {
                    "status": "completed",
                    "completed_at": completed_at,
                    "result_summary": {
                        **previous_summary,
                        "summary": summary,
                        "metrics": dict(previous_summary.get("metrics") or {"status": "skeleton_ready"}),
                        "replay_samples": list(previous_summary.get("replay_samples") or []),
                        "artifacts": list(previous_summary.get("artifacts") or []),
                        "logs": list(previous_summary.get("logs") or ["online validation skeleton execution completed"]),
                    },
                },
            )
            await session.commit()

    async def _require_dataset(self, dataset_id: str):
        row = await self._datasets.get(org_id=self._org_id, dataset_id=dataset_id, owner_user_id=self._user_id)
        if row is None:
            raise NotFoundError("dataset not found")
        return row

    async def _require_dataset_active(self, dataset_id: str):
        row = await self._require_dataset(dataset_id)
        if str(getattr(row, "status", "") or "").lower() != "active":
            raise ValidationError("dataset must be active")
        return row

    async def _require_generic_resource(self, *, resource_type: str, resource_id: str):
        model = RESOURCE_MODEL_MAP[resource_type]
        row = await self._resources.get(model=model, org_id=self._org_id, resource_id=resource_id, owner_user_id=self._user_id)
        if row is None:
            raise NotFoundError(f"{resource_type} not found")
        return row

    async def _commit(self) -> None:
        commit = getattr(self._session, "commit", None)
        if commit is None:
            return
        result = commit()
        if asyncio.iscoroutine(result):
            await result

    async def _resolve_execution_mode(self) -> str:
        result = has_active_celery_worker()
        if inspect.isawaitable(result):
            result = await result
        return "celery" if result else "local_background"

    async def _require_processing_resource(self, *, dataset_id: str, processing_type: str):
        await self._require_dataset(dataset_id)
        model = PROCESSING_MODEL_MAP[processing_type]
        rows, _ = await self._resources.list_for_owner(
            model=model,
            org_id=self._org_id,
            owner_user_id=self._user_id,
            page=1,
            size=1,
            extra_filters=[model.dataset_id == dataset_id],
        )
        if not rows:
            raise NotFoundError(f"{processing_type} resource not found")
        return rows[0]

    async def _resolve_eval_item_payloads(
        self,
        *,
        dataset_id: str,
        sample_ids: list[str],
        existing_items: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not sample_ids:
            raise ValidationError("sample_ids cannot be empty")
        rows = await self._dataset_samples.list_for_dataset_all(
            org_id=self._org_id,
            dataset_id=dataset_id,
            owner_user_id=self._user_id,
        )
        row_map = {row.id: row for row in rows}
        existing_snapshot_map = {
            item.dataset_sample_id: item
            for item in (existing_items or [])
            if item.dataset_sample_id and item.deleted_at is None
        }
        missing = [sample_id for sample_id in sample_ids if sample_id not in row_map and sample_id not in existing_snapshot_map]
        if missing:
            raise ValidationError("some sample_ids do not belong to source dataset")
        payloads: list[dict[str, Any]] = []
        for sample_id in sample_ids:
            live_sample = row_map.get(sample_id)
            if live_sample is not None:
                payloads.append(
                    {
                        "dataset_sample_id": live_sample.id,
                        "payload_json": {
                            "sample_type": live_sample.sample_type,
                            "sample_name": live_sample.sample_name,
                            "preview_text": live_sample.preview_text,
                            "text_content": live_sample.text_content,
                            "file_url": live_sample.file_url,
                            "annotation_data": live_sample.annotation_data,
                            "source_metadata": live_sample.source_metadata,
                        },
                    }
                )
                continue
            snapshot_item = existing_snapshot_map[sample_id]
            payloads.append(
                {
                    "dataset_sample_id": snapshot_item.dataset_sample_id,
                    "payload_json": dict(snapshot_item.payload_json or {}),
                }
            )
        return payloads

    async def _require_target_resource(self, target_type: str, target_id: str):
        mapping = {
            "training_job": "training_job",
            "fine_tune": "fine_tune",
            "deployment": "deployment",
        }
        if target_type not in mapping:
            raise ValidationError("unsupported target_type")
        return await self._require_generic_resource(resource_type=mapping[target_type], resource_id=target_id)

    async def _require_completed_target_resource(self, target_type: str, target_id: str):
        row = await self._require_target_resource(target_type, target_id)
        if str(getattr(row, "status", "") or "") != "completed":
            raise ValidationError("target resource must be completed")
        return row

    async def _require_completed_resource(self, *, resource_type: str, resource_id: str):
        row = await self._require_generic_resource(resource_type=resource_type, resource_id=resource_id)
        if str(getattr(row, "status", "") or "") != "completed":
            raise ValidationError(f"{resource_type} must be completed")
        return row

    async def _select_validation_replay_task_ids(self, *, limit: int = 5) -> list[str]:
        task_rows, _ = await self._task_repo.list_paged(
            org_id=self._org_id,
            filters={"status": "done"},
            page=1,
            size=limit,
            owner_user_id=None,
        )
        return [row.id for row in task_rows[:limit]]

    async def _build_validation_replay_tasks(self, task_ids: list[str]) -> list[dict[str, Any]]:
        if not task_ids:
            return []
        replay_tasks: list[dict[str, Any]] = []
        for task_id in task_ids:
            task = await self._task_repo.get(self._org_id, task_id)
            if task is None or str(getattr(task, "status", "") or "") != "done":
                continue
            result = await self._result_repo.get_by_task(self._org_id, task_id)
            replay_tasks.append(
                {
                    "task_id": task.id,
                    "product_id": task.product_id,
                    "spec_code": task.spec_code,
                    "verdict": getattr(result, "verdict", None),
                    "overall_score": float(getattr(result, "overall_score", 0.0) or 0.0),
                }
            )
        return replay_tasks

    async def _require_training_model_config(self, model_config_id: str):
        model = await self._model_configs.get(self._org_id, model_config_id)
        if model is None:
            raise NotFoundError("model config not found")
        if not model.is_active:
            raise ValidationError("model config is inactive")
        if str(model.model_type or "").lower() not in {"chat", "multimodal"}:
            raise ValidationError("training and fine-tune only support chat or multimodal models")
        return model

    async def _require_kg_entity(self, entity_id: str):
        entity = await self._kg_repo.get_entity(org_id=self._org_id, entity_id=entity_id, created_by=self._user_id)
        if entity is None:
            raise NotFoundError("knowledge graph entity not found")
        return entity

    async def _require_dataset_sample(self, *, dataset_id: str, sample_id: str, sample_type: str | None = None):
        sample = await self._dataset_samples.get(
            org_id=self._org_id,
            dataset_id=dataset_id,
            sample_id=sample_id,
            owner_user_id=self._user_id,
        )
        if sample is None:
            raise NotFoundError("dataset sample not found")
        if sample_type and str(getattr(sample, "sample_type", "") or "") != sample_type:
            raise ValidationError(f"sample must be {sample_type}")
        return sample

    async def _get_active_embedding_model(self, config_json: dict[str, Any] | None = None) -> dict[str, Any] | None:
        requested_model_id = str((config_json or {}).get("embedding_model_id") or "").strip()
        if requested_model_id:
            model = await self._model_configs.get(self._org_id, requested_model_id)
            if model and model.is_active and str(model.model_type or "").lower() in {"embedding", "embed", "text_embedding"}:
                return {
                    "id": model.id,
                    "display_name": model.display_name,
                    "model_key": model.model_key,
                    "provider": model.provider,
                    "priority": model.priority,
                }
        models = await self._model_configs.list_active(self._org_id)
        for model in sorted(models, key=lambda item: int(item.priority or 0)):
            if str(model.model_type or "").lower() in {"embedding", "embed", "text_embedding"}:
                return {
                    "id": model.id,
                    "display_name": model.display_name,
                    "model_key": model.model_key,
                    "provider": model.provider,
                    "priority": model.priority,
                }
        return None

    @staticmethod
    def _ensure_processing_resource_editable(resource) -> None:
        if str(getattr(resource, "status", "") or "") in {"queued", "running"}:
            raise ValidationError("processing resource is not editable while queued or running")

    @staticmethod
    async def _ensure_editable(status: str) -> None:
        if status not in EDITABLE_STATUSES:
            raise ValidationError("resource can only be edited in draft or failed status")

    @staticmethod
    def _normalize_updates(updates: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(updates)
        if "name" in normalized and normalized["name"] is not None:
            normalized["name"] = str(normalized["name"]).strip()
        if "description" in normalized:
            normalized["description"] = (normalized["description"] or "").strip() or None
        return normalized

    async def _build_model_ref(self, model_config_id: str | None) -> ResourceModelRef | None:
        if not model_config_id:
            return None
        model = await self._model_configs.get(self._org_id, model_config_id)
        if model is None:
            return None
        return ResourceModelRef(
            id=model.id,
            display_name=model.display_name,
            model_key=model.model_key,
            model_type=model.model_type,
        )

    def _to_execution_model_ref(self, model) -> ExecutionModelRef | None:
        if model is None:
            return None
        return ExecutionModelRef(
            id=model.id,
            provider=getattr(model, "provider", None),
            model_key=getattr(model, "model_key", None),
            display_name=getattr(model, "display_name", None),
            endpoint=getattr(model, "endpoint", None),
            model_type=getattr(model, "model_type", None),
        )

    async def _resolve_model_ref_for_resource(self, row) -> ExecutionModelRef | None:
        model_config_id = getattr(row, "model_config_id", None)
        if model_config_id:
            model = await self._model_configs.get(self._org_id, model_config_id)
            return self._to_execution_model_ref(model)
        summary = dict(getattr(row, "result_summary", None) or {})
        nested_summary = dict(summary.get("summary") or {})
        model_key = nested_summary.get("model_key")
        model_config_id = nested_summary.get("model_config_id")
        if model_config_id:
            model = await self._model_configs.get(self._org_id, model_config_id)
            return self._to_execution_model_ref(model)
        if model_key:
            return ExecutionModelRef(
                id=None,
                provider=None,
                model_key=str(model_key),
                display_name=str(model_key),
                endpoint=None,
            )
        return None

    async def _build_training_job_response(self, row) -> TrainingJobResponse:
        payload = TrainingJobResponse.model_validate(row).model_dump()
        payload["result_summary"] = dict(payload.get("result_summary") or self._default_training_job_summary())
        model_ref = await self._build_model_ref(getattr(row, "model_config_id", None))
        payload["model_config_ref"] = model_ref.model_dump() if model_ref else None
        return TrainingJobResponse(**payload)

    async def _build_fine_tune_response(self, row) -> FineTuneRunResponse:
        payload = FineTuneRunResponse.model_validate(row).model_dump()
        payload["result_summary"] = dict(payload.get("result_summary") or self._default_training_job_summary())
        model_ref = await self._build_model_ref(getattr(row, "model_config_id", None))
        payload["model_config_ref"] = model_ref.model_dump() if model_ref else None
        return FineTuneRunResponse(**payload)

    async def _build_experiment_response(self, row) -> ExperimentResponse:
        payload = ExperimentResponse.model_validate(row).model_dump()
        related_resources, artifacts = await self._build_experiment_related_resources(row.id)
        payload["related_resources"] = related_resources.model_dump()
        payload["result_summary"] = self._build_experiment_result_summary(related_resources, artifacts)
        return ExperimentResponse(**payload)

    @staticmethod
    def _build_experiment_result_summary(
        related_resources: ExperimentRelatedResources,
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        counts = {
            "training_jobs": len(related_resources.training_jobs),
            "fine_tunes": len(related_resources.fine_tunes),
            "offline_evaluations": len(related_resources.offline_evaluations),
            "deployments": len(related_resources.deployments),
        }
        latest_lines = [
            f"训练任务数={counts['training_jobs']}",
            f"微调任务数={counts['fine_tunes']}",
            f"离线评测数={counts['offline_evaluations']}",
            f"部署数={counts['deployments']}",
        ]
        latest_status = next(
            (
                item.status
                for bucket in (
                    related_resources.deployments,
                    related_resources.offline_evaluations,
                    related_resources.fine_tunes,
                    related_resources.training_jobs,
                )
                for item in bucket
                if item.status
            ),
            "draft",
        )
        return {
            "summary": {
                "status": latest_status,
                "训练任务数": counts["training_jobs"],
                "微调任务数": counts["fine_tunes"],
                "离线评测数": counts["offline_evaluations"],
                "部署数": counts["deployments"],
            },
            "metrics": counts,
            "artifacts": artifacts,
            "logs": latest_lines,
        }

    async def _build_experiment_related_resources(self, experiment_id: str) -> tuple[ExperimentRelatedResources, list[dict[str, Any]]]:
        artifacts: list[dict[str, Any]] = []

        async def build_items(resource_type: str, metric_keys: list[str]) -> list[ExperimentRelatedResourceSummary]:
            model = RESOURCE_MODEL_MAP[resource_type]
            rows, _ = await self._resources.list_for_owner(
                model=model,
                org_id=self._org_id,
                owner_user_id=self._user_id,
                page=1,
                size=100,
                extra_filters=[model.experiment_id == experiment_id],
            )
            items: list[ExperimentRelatedResourceSummary] = []
            for resource in rows:
                summary = dict(getattr(resource, "result_summary", None) or {})
                metrics = dict(summary.get("metrics") or {})
                metric_excerpt = {key: metrics.get(key) for key in metric_keys if key in metrics}
                if not metric_excerpt and isinstance(metrics.get("summary"), dict):
                    metric_excerpt = dict(metrics.get("summary") or {})
                if resource_type == "deployment":
                    metric_excerpt = dict(summary.get("runtime_registration") or {})
                source_artifacts = list(summary.get("artifacts") or [])
                if not source_artifacts and isinstance(metrics.get("summary"), dict):
                    source_artifacts = list((metrics.get("summary") or {}).get("artifacts") or [])
                for artifact in source_artifacts:
                    if isinstance(artifact, dict):
                        artifacts.append(
                            {
                                "source_type": resource_type,
                                "source_id": resource.id,
                                "source_name": resource.name,
                                **artifact,
                            }
                        )
                items.append(
                    ExperimentRelatedResourceSummary(
                        id=resource.id,
                        name=resource.name,
                        status=resource.status,
                        metrics=metric_excerpt,
                        updated_at=getattr(resource, "updated_at", None),
                    )
            )
            return items

        return ExperimentRelatedResources(
            training_jobs=await build_items("training_job", ["accuracy", "f1", "mAP", "IoU", "AR"]),
            fine_tunes=await build_items("fine_tune", ["accuracy", "f1", "mAP", "IoU", "AR"]),
            offline_evaluations=await build_items("offline_evaluation", ["accuracy", "f1", "mAP", "IoU", "AR"]),
            deployments=await build_items("deployment", []),
        ), artifacts

    async def _build_evaluation_dataset_response(self, row) -> EvaluationDatasetResponse:
        sample_count = await self._eval_items.count_items(
            org_id=self._org_id,
            evaluation_dataset_id=row.id,
            created_by=self._user_id,
        )
        preview_rows, _ = await self._eval_items.list_items(
            org_id=self._org_id,
            evaluation_dataset_id=row.id,
            created_by=self._user_id,
            page=1,
            size=6,
        )
        payload = EvaluationDatasetResponse.model_validate(row).model_dump()
        payload["sample_count"] = sample_count
        payload["samples_preview"] = [item.model_dump() for item in await self._serialize_evaluation_dataset_items(row.source_dataset_id, preview_rows)]
        return EvaluationDatasetResponse(**payload)

    async def _serialize_evaluation_dataset_items(
        self,
        source_dataset_id: str,
        items: list[Any],
    ) -> list[EvaluationDatasetItemResponse]:
        source_rows = await self._dataset_samples.list_for_dataset_all(
            org_id=self._org_id,
            dataset_id=source_dataset_id,
            owner_user_id=self._user_id,
        )
        source_map = {row.id: row for row in source_rows}
        serialized: list[EvaluationDatasetItemResponse] = []
        for item in items:
            snapshot = dict(item.payload_json or {})
            sample = source_map.get(item.dataset_sample_id or "")
            data = {
                "id": item.id,
                "org_id": item.org_id,
                "evaluation_dataset_id": item.evaluation_dataset_id,
                "source_dataset_id": item.source_dataset_id,
                "dataset_sample_id": item.dataset_sample_id,
                "created_by": item.created_by,
                "item_order": item.item_order,
                "sample_type": snapshot.get("sample_type") or getattr(sample, "sample_type", "text"),
                "sample_name": snapshot.get("sample_name") if sample is None else sample.sample_name,
                "preview_text": snapshot.get("preview_text") if sample is None else sample.preview_text,
                "text_content": snapshot.get("text_content") if sample is None else sample.text_content,
                "file_url": snapshot.get("file_url") if sample is None else sample.file_url,
                "annotation_data": snapshot.get("annotation_data") if sample is None else sample.annotation_data,
                "source_metadata": snapshot.get("source_metadata") if sample is None else sample.source_metadata,
                "snapshot_deleted_from_source": sample is None,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            serialized.append(EvaluationDatasetItemResponse(**data))
        return serialized

    @staticmethod
    def _default_processing_summary(processing_type: str) -> dict[str, Any]:
        base = {
            "summary": {"status": "queued", "current_stats": {}, "degraded_mode": False, "degraded_reason": None},
            "current_stats": {},
            "warnings": [],
            "phases": AlgoWorkspaceService._default_phases(processing_type),
            "progress": 0,
        }
        if processing_type == "kg":
            return {**base, "entities": [], "relations": []}
        if processing_type == "alignment":
            return {**base, "pairs": []}
        if processing_type == "augmentation":
            return {**base, "proposals": []}
        return {**base, "artifact": None}

    @staticmethod
    def _default_phases(processing_type: str) -> list[dict[str, Any]]:
        phase_map = {
            "kg": ["scan_samples", "extract_entities", "extract_relations", "persist_graph"],
            "alignment": ["describe_samples", "embed_or_fallback", "score_pairs", "persist_pairs"],
            "augmentation": ["generate_proposals", "preview", "apply"],
            "export": ["collect_samples", "build_vlm_json", "write_artifact"],
        }
        return [{"name": name, "status": "pending"} for name in phase_map.get(processing_type, [])]

    @staticmethod
    def _default_training_job_summary(
        *,
        status: str = "draft",
        execution_mode: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        model_config_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "summary": {
                "status": status,
                "execution_mode": execution_mode,
                "started_at": started_at.isoformat() if started_at else None,
                "completed_at": completed_at.isoformat() if completed_at else None,
                "model_config_id": model_config_id,
            },
            "artifacts": [],
            "metrics": {},
            "logs": [],
        }

    async def _serialize_generic_resource(self, resource_type: str, row):
        if resource_type == "evaluation_dataset":
            return EvaluationDatasetResponse(
                **AlgoResourceResponse.model_validate(row).model_dump(),
                source_dataset_id=row.source_dataset_id,
                sample_count=0,
            )
        serializer_map = {
            "training_job": TrainingJobResponse,
            "fine_tune": FineTuneRunResponse,
            "offline_evaluation": OfflineEvaluationResponse,
            "online_validation": OnlineValidationResponse,
            "experiment": ExperimentResponse,
            "deployment": ModelDeploymentResponse,
        }
        if resource_type == "training_job":
            return await self._build_training_job_response(row)
        if resource_type == "fine_tune":
            return await self._build_fine_tune_response(row)
        if resource_type == "experiment":
            return await self._build_experiment_response(row)
        if resource_type == "offline_evaluation":
            payload = OfflineEvaluationResponse.model_validate(row).model_dump()
            payload["result_summary"] = dict(payload.get("result_summary") or self._default_offline_evaluation_summary())
            return OfflineEvaluationResponse(**payload)
        if resource_type == "deployment":
            payload = ModelDeploymentResponse.model_validate(row).model_dump()
            payload["result_summary"] = dict(payload.get("result_summary") or self._default_deployment_summary())
            return ModelDeploymentResponse(**payload)
        serializer = serializer_map[resource_type]
        return serializer.model_validate(row)

    def _require_deployable_artifacts(self, result_summary: dict[str, Any] | None, label: str) -> None:
        artifacts = list((result_summary or {}).get("artifacts") or [])
        has_model_artifact = any(str(item.get("type") or "") in {"best_model", "checkpoint", "deployed_model"} for item in artifacts)
        if not has_model_artifact:
            raise ValidationError(f"{label} does not contain deployable artifacts")

    def _default_offline_evaluation_summary(
        self,
        *,
        status: str = "draft",
        execution_mode: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        return {
            "summary": {
                "status": status,
                "execution_mode": execution_mode,
                "started_at": _iso_dt(started_at),
                "completed_at": _iso_dt(completed_at),
            },
            "metrics": {},
            "error_cases": [],
            "artifacts": [],
            "logs": [],
        }

    def _default_deployment_summary(
        self,
        *,
        status: str = "draft",
        execution_mode: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        return {
            "summary": {
                "status": status,
                "execution_mode": execution_mode,
                "started_at": _iso_dt(started_at),
                "completed_at": _iso_dt(completed_at),
            },
            "runtime_registration": {},
            "artifacts": [],
            "logs": [],
        }

    def _default_generic_execution_summary(self, resource_type: str) -> dict[str, Any]:
        if resource_type == "offline_evaluation":
            return self._default_offline_evaluation_summary(status="queued")
        if resource_type == "deployment":
            return self._default_deployment_summary(status="queued")
        if resource_type == "online_validation":
            return {
                "summary": {
                    "status": "queued",
                    "execution_mode": None,
                    "started_at": None,
                    "completed_at": None,
                    "deployment_id": None,
                    "validation_type": "shadow",
                    "replay_source": "historical_tasks",
                    "replay_count": 0,
                },
                "metrics": {},
                "replay_samples": [],
                "artifacts": [],
                "logs": [],
            }
        return {"artifacts": [], "metrics": {}, "logs": []}

    def _default_generic_completion_summary(self, resource_type: str, previous_summary: dict[str, Any] | None) -> dict[str, Any]:
        if resource_type == "online_validation":
            summary = dict((previous_summary or {}).get("summary") or {})
            summary.update(
                {
                    "status": "completed",
                    "completed_at": summary.get("completed_at"),
                }
            )
            return {
                **dict(previous_summary or {}),
                "summary": summary,
                "artifacts": list((previous_summary or {}).get("artifacts") or []),
                "metrics": dict((previous_summary or {}).get("metrics") or {"status": "skeleton_ready"}),
                "replay_samples": list((previous_summary or {}).get("replay_samples") or []),
                "logs": list((previous_summary or {}).get("logs") or ["online validation skeleton execution completed"]),
            }
        return dict(previous_summary or self._default_generic_execution_summary(resource_type))


async def run_algo_processing_pipeline(
    *,
    org_id: str,
    user_id: str,
    dataset_id: str,
    processing_type: str,
    resource_id: str,
    job_id: str,
    mode: str,
) -> dict[str, str]:
    async with get_session() as session:
        service = AlgoWorkspaceService(session, org_id, user_id)
        await service._run_processing(
            processing_type=processing_type,
            dataset_id=dataset_id,
            resource_id=resource_id,
            job_id=job_id,
            mode=mode,
        )
    return {"status": "ok"}


async def run_algo_resource_pipeline(
    *,
    org_id: str,
    user_id: str,
    resource_type: str,
    resource_id: str,
    mode: str,
) -> dict[str, str]:
    async with get_session() as session:
        service = AlgoWorkspaceService(session, org_id, user_id)
        if resource_type == "fine_tune":
            await service._run_fine_tune_job(resource_id=resource_id, mode=mode)
        elif resource_type == "offline_evaluation":
            await service._run_offline_evaluation_job(resource_id=resource_id, mode=mode)
        elif resource_type == "deployment":
            await service._run_deployment_job(resource_id=resource_id, mode=mode)
        elif resource_type == "training_job":
            await service._run_training_job(resource_id=resource_id, mode=mode)
        else:
            await service._run_generic_resource(resource_type=resource_type, resource_id=resource_id, mode=mode)
    return {"status": "ok"}
