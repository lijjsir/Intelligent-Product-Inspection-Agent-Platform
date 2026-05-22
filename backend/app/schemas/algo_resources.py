from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import PageParams, PagedResponse


ResourceStatus = Literal["draft", "queued", "running", "completed", "failed", "cancelled"]
ProcessingTab = Literal["kg", "alignment", "augmentation", "export"]


class AlgoResourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    config_json: dict[str, Any] | None = None


class AlgoResourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    config_json: dict[str, Any] | None = None


class AlgoResourceResponse(BaseModel):
    id: str
    org_id: str
    created_by: str | None = None
    name: str
    description: str | None = None
    status: ResourceStatus
    config_json: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AlgoExecutionResourceResponse(AlgoResourceResponse):
    execution_mode: str | None = None
    executor_job_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class DatasetProcessingRunRequest(AlgoResourceBase):
    pass


class DatasetKgEntityCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(default="Entity", min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    properties_json: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class DatasetKgRelationCreateRequest(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relation_type: str = Field(default="RELATED_TO", min_length=1, max_length=64)
    properties_json: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class DatasetKgEntityResponse(BaseModel):
    id: str
    org_id: str
    dataset_id: str
    knowledge_graph_id: str
    created_by: str | None = None
    name: str
    entity_type: str
    description: str | None = None
    properties_json: dict[str, Any] | None = None
    confidence: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DatasetKgRelationResponse(BaseModel):
    id: str
    org_id: str
    dataset_id: str
    knowledge_graph_id: str
    created_by: str | None = None
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    properties_json: dict[str, Any] | None = None
    confidence: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DatasetAlignmentPairCreateRequest(BaseModel):
    source_sample_id: str | None = None
    target_sample_id: str | None = None
    relation_type: str = Field(default="describes", min_length=1, max_length=64)
    similarity_score: float | None = Field(default=None, ge=0, le=1)
    payload_json: dict[str, Any] | None = None


class DatasetAlignmentPairResponse(BaseModel):
    id: str
    org_id: str
    dataset_id: str
    alignment_id: str
    created_by: str | None = None
    source_sample_id: str | None = None
    target_sample_id: str | None = None
    relation_type: str
    similarity_score: float | None = None
    payload_json: dict[str, Any] | None = None
    confirmation_status: str = "suggested"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DatasetAugmentationProposalCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    config_json: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None
    source_sample_id: str | None = None
    augmentation_method: str | None = Field(default=None, max_length=64)
    augmentation_params: dict[str, Any] | None = None


class DatasetAugmentationProposalResponse(AlgoResourceResponse):
    dataset_id: str
    batch_id: str
    source_sample_id: str | None = None
    augmentation_method: str | None = None
    augmentation_params: dict[str, Any] | None = None
    created_sample_id: str | None = None
    created_sample_ids: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class DatasetExportRequest(AlgoResourceBase):
    format: str = Field(default="vlm-json", max_length=32)
    train_ratio: float = Field(default=0.7, ge=0, le=1)
    val_ratio: float = Field(default=0.15, ge=0, le=1)
    test_ratio: float = Field(default=0.15, ge=0, le=1)
    include_augmented: bool = True
    only_confirmed_alignment: bool = False


class DatasetProcessingSubgraphRequest(BaseModel):
    entity_type: str | None = None
    keyword: str | None = None


class DatasetProcessingStatusResponse(BaseModel):
    resource: AlgoResourceResponse | None = None
    latest_job: dict[str, Any] | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    phases: list[dict[str, Any]] = Field(default_factory=list)
    progress: int = 0
    warnings: list[str] = Field(default_factory=list)


class EvaluationDatasetCreateRequest(AlgoResourceBase):
    source_dataset_id: str
    sample_ids: list[str] = Field(..., min_length=1, max_length=2000)


class EvaluationDatasetUpdateRequest(AlgoResourceUpdateRequest):
    sample_ids: list[str] | None = Field(default=None, max_length=2000)


class EvaluationDatasetSampleAppendRequest(BaseModel):
    sample_ids: list[str] = Field(..., min_length=1, max_length=2000)


class EvaluationDatasetItemListQuery(PageParams):
    sample_type: Literal["image", "text"] | None = None


class EvaluationDatasetItemResponse(BaseModel):
    id: str
    org_id: str
    evaluation_dataset_id: str
    source_dataset_id: str
    dataset_sample_id: str | None = None
    created_by: str | None = None
    item_order: int
    sample_type: Literal["image", "text"]
    sample_name: str | None = None
    preview_text: str | None = None
    text_content: str | None = None
    file_url: str | None = None
    annotation_data: dict[str, Any] | list[Any] | None = None
    source_metadata: dict[str, Any] | None = None
    snapshot_deleted_from_source: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class EvaluationDatasetResponse(AlgoResourceResponse):
    source_dataset_id: str
    sample_count: int = 0
    samples_preview: list[EvaluationDatasetItemResponse] = Field(default_factory=list)


class ResourceModelRef(BaseModel):
    id: str
    display_name: str
    model_key: str
    model_type: str


class ExperimentRelatedResourceSummary(BaseModel):
    id: str
    name: str
    status: ResourceStatus
    metrics: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class ExperimentRelatedResources(BaseModel):
    training_jobs: list[ExperimentRelatedResourceSummary] = Field(default_factory=list)
    fine_tunes: list[ExperimentRelatedResourceSummary] = Field(default_factory=list)
    offline_evaluations: list[ExperimentRelatedResourceSummary] = Field(default_factory=list)
    deployments: list[ExperimentRelatedResourceSummary] = Field(default_factory=list)


class TrainingJobCreateRequest(AlgoResourceBase):
    source_dataset_id: str
    model_config_id: str
    eval_set_id: str | None = None
    experiment_id: str | None = None


class TrainingJobUpdateRequest(AlgoResourceUpdateRequest):
    model_config_id: str | None = None
    eval_set_id: str | None = None
    experiment_id: str | None = None


class TrainingJobResponse(AlgoExecutionResourceResponse):
    source_dataset_id: str
    model_config_id: str
    model_config_ref: ResourceModelRef | None = None
    eval_set_id: str | None = None
    experiment_id: str | None = None


class FineTuneRunCreateRequest(AlgoResourceBase):
    training_job_id: str
    model_config_id: str
    experiment_id: str | None = None


class FineTuneRunUpdateRequest(AlgoResourceUpdateRequest):
    model_config_id: str | None = None
    experiment_id: str | None = None


class FineTuneRunResponse(AlgoExecutionResourceResponse):
    training_job_id: str
    model_config_id: str
    model_config_ref: ResourceModelRef | None = None
    experiment_id: str | None = None


class OfflineEvaluationCreateRequest(AlgoResourceBase):
    eval_set_id: str
    target_type: str = Field(..., min_length=1, max_length=64)
    target_id: str
    experiment_id: str | None = None


class OfflineEvaluationUpdateRequest(AlgoResourceUpdateRequest):
    experiment_id: str | None = None


class OfflineEvaluationResponse(AlgoExecutionResourceResponse):
    eval_set_id: str
    target_type: str
    target_id: str
    experiment_id: str | None = None


class OnlineValidationCreateRequest(AlgoResourceBase):
    deployment_id: str
    experiment_id: str | None = None


class OnlineValidationUpdateRequest(AlgoResourceUpdateRequest):
    experiment_id: str | None = None


class OnlineValidationResponse(AlgoExecutionResourceResponse):
    deployment_id: str
    experiment_id: str | None = None


class ExperimentCreateRequest(AlgoResourceBase):
    pass


class ExperimentUpdateRequest(AlgoResourceUpdateRequest):
    pass


class ExperimentResponse(AlgoResourceResponse):
    related_resources: ExperimentRelatedResources = Field(default_factory=ExperimentRelatedResources)


class ModelDeploymentCreateRequest(AlgoResourceBase):
    source_type: str = Field(..., min_length=1, max_length=64)
    source_id: str
    experiment_id: str | None = None


class ModelDeploymentUpdateRequest(AlgoResourceUpdateRequest):
    experiment_id: str | None = None


class ModelDeploymentResponse(AlgoExecutionResourceResponse):
    source_type: str
    source_id: str
    experiment_id: str | None = None


class ResourceActionResponse(BaseModel):
    id: str
    status: ResourceStatus
    execution_mode: str | None = None
    executor_job_id: str | None = None


class AlgoResourceListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
    keyword: str | None = Field(default=None, max_length=255)
    status: ResourceStatus | None = None


class ProcessingListQuery(AlgoResourceListQuery):
    pass


class AlgoResourceListResponse(PagedResponse[AlgoResourceResponse]):
    pass


class AlgoExecutionResourceListResponse(PagedResponse[AlgoExecutionResourceResponse]):
    pass


class EvaluationDatasetListResponse(PagedResponse[EvaluationDatasetResponse]):
    pass


class TrainingJobListResponse(PagedResponse[TrainingJobResponse]):
    pass


class FineTuneRunListResponse(PagedResponse[FineTuneRunResponse]):
    pass


class OfflineEvaluationListResponse(PagedResponse[OfflineEvaluationResponse]):
    pass


class OnlineValidationListResponse(PagedResponse[OnlineValidationResponse]):
    pass


class ExperimentListResponse(PagedResponse[ExperimentResponse]):
    pass


class ModelDeploymentListResponse(PagedResponse[ModelDeploymentResponse]):
    pass


class DatasetProcessingResultsResponse(BaseModel):
    summary: dict[str, Any] = Field(default_factory=dict)
    entities: list[DatasetKgEntityResponse] = Field(default_factory=list)
    relations: list[DatasetKgRelationResponse] = Field(default_factory=list)
    pairs: list[DatasetAlignmentPairResponse] = Field(default_factory=list)
    proposals: list[DatasetAugmentationProposalResponse] = Field(default_factory=list)
    artifact: dict[str, Any] | None = None


class DatasetProcessingManualDeleteResponse(BaseModel):
    deleted: bool
