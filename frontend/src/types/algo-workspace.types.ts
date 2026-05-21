import type { PageParams, PagedResponse } from "./common.types";
import type { DatasetSampleType } from "./dataset.types";

export type AlgoResourceStatus = "draft" | "queued" | "running" | "completed" | "failed" | "cancelled";
export type DatasetProcessingType = "kg" | "alignment" | "augmentation" | "export";

export interface AlgoResourceBase {
  id: string;
  org_id: string;
  created_by?: string | null;
  name: string;
  description?: string | null;
  status: AlgoResourceStatus;
  config_json?: Record<string, unknown> | null;
  result_summary?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AlgoExecutionResource extends AlgoResourceBase {
  execution_mode?: string | null;
  executor_job_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface DatasetProcessingRunRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
}

export interface DatasetProcessingStatus {
  resource?: AlgoResourceBase | null;
  latest_job?: {
    id: string;
    status: string;
    job_type: string;
    result_summary?: Record<string, unknown> | null;
    created_at?: string | null;
  } | null;
  summary: Record<string, unknown>;
  phases?: Array<{ name: string; status: string }>;
  progress?: number;
  warnings?: string[];
}

export interface KnowledgeGraphEntity {
  id: string;
  org_id: string;
  dataset_id: string;
  knowledge_graph_id: string;
  created_by?: string | null;
  name: string;
  entity_type: string;
  description?: string | null;
  properties_json?: Record<string, unknown> | null;
  confidence?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface KnowledgeGraphRelation {
  id: string;
  org_id: string;
  dataset_id: string;
  knowledge_graph_id: string;
  created_by?: string | null;
  source_entity_id: string;
  target_entity_id: string;
  relation_type: string;
  properties_json?: Record<string, unknown> | null;
  confidence?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AlignmentPair {
  id: string;
  org_id: string;
  dataset_id: string;
  alignment_id: string;
  created_by?: string | null;
  source_sample_id?: string | null;
  target_sample_id?: string | null;
  relation_type: string;
  similarity_score?: number | null;
  payload_json?: Record<string, unknown> | null;
  confirmation_status?: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AugmentationProposal extends AlgoResourceBase {
  dataset_id: string;
  batch_id: string;
  source_sample_id?: string | null;
  augmentation_method?: string | null;
  augmentation_params?: Record<string, unknown> | null;
}

export interface DatasetProcessingSubgraphNode {
  id: string;
  name: string;
  entity_type: string;
  value: number;
  description?: string | null;
  properties_json?: Record<string, unknown>;
}

export interface DatasetProcessingSubgraphEdge {
  id: string;
  source: string;
  target: string;
  relation_type: string;
  value: number;
  properties_json?: Record<string, unknown>;
}

export interface DatasetProcessingSubgraph {
  nodes: DatasetProcessingSubgraphNode[];
  edges: DatasetProcessingSubgraphEdge[];
  stats: Record<string, unknown>;
}

export interface DatasetProcessingResults {
  summary: Record<string, unknown>;
  entities: KnowledgeGraphEntity[];
  relations: KnowledgeGraphRelation[];
  pairs: AlignmentPair[];
  proposals: AugmentationProposal[];
  artifact?: Record<string, unknown> | null;
}

export interface EvaluationDataset extends AlgoResourceBase {
  source_dataset_id: string;
  sample_count: number;
  samples_preview: EvaluationDatasetItem[];
}

export interface EvaluationDatasetItem {
  id: string;
  org_id: string;
  evaluation_dataset_id: string;
  source_dataset_id: string;
  dataset_sample_id?: string | null;
  created_by?: string | null;
  item_order: number;
  sample_type: DatasetSampleType;
  sample_name?: string | null;
  preview_text?: string | null;
  text_content?: string | null;
  file_url?: string | null;
  annotation_data?: Record<string, unknown> | unknown[] | null;
  source_metadata?: Record<string, unknown> | null;
  snapshot_deleted_from_source: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ResourceModelRef {
  id: string;
  display_name: string;
  model_key: string;
  model_type: string;
}

export interface TrainingJob extends AlgoExecutionResource {
  source_dataset_id: string;
  model_config_id: string;
  model_config_ref?: ResourceModelRef | null;
  eval_set_id?: string | null;
  experiment_id?: string | null;
}

export interface FineTuneRun extends AlgoExecutionResource {
  training_job_id: string;
  model_config_id: string;
  model_config_ref?: ResourceModelRef | null;
  experiment_id?: string | null;
}

export interface OfflineEvaluation extends AlgoExecutionResource {
  eval_set_id: string;
  target_type: string;
  target_id: string;
  experiment_id?: string | null;
}

export interface OnlineValidation extends AlgoExecutionResource {
  deployment_id: string;
  experiment_id?: string | null;
}

export interface Experiment extends AlgoResourceBase {}

export interface Deployment extends AlgoExecutionResource {
  source_type: string;
  source_id: string;
  experiment_id?: string | null;
}

export interface AlgoResourceActionResponse {
  id: string;
  status: AlgoResourceStatus;
  execution_mode?: string | null;
  executor_job_id?: string | null;
}

export interface AlgoListQuery extends PageParams {
  keyword?: string;
  status?: AlgoResourceStatus | "";
}

export interface EvaluationDatasetCreateRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
  source_dataset_id: string;
  sample_ids: string[];
}

export interface EvaluationDatasetUpdateRequest {
  name?: string;
  description?: string | null;
  config_json?: Record<string, unknown>;
  sample_ids?: string[];
}

export interface EvaluationDatasetSampleAppendRequest {
  sample_ids: string[];
}

export interface EvaluationDatasetItemListQuery extends PageParams {
  sample_type?: DatasetSampleType | "";
}

export interface TrainingJobCreateRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
  source_dataset_id: string;
  model_config_id: string;
  eval_set_id?: string | null;
  experiment_id?: string | null;
}

export interface TrainingJobUpdateRequest {
  name?: string;
  description?: string | null;
  config_json?: Record<string, unknown>;
  model_config_id?: string | null;
  eval_set_id?: string | null;
  experiment_id?: string | null;
}

export interface FineTuneRunCreateRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
  training_job_id: string;
  model_config_id: string;
  experiment_id?: string | null;
}

export interface FineTuneRunUpdateRequest {
  name?: string;
  description?: string | null;
  config_json?: Record<string, unknown>;
  model_config_id?: string | null;
  experiment_id?: string | null;
}

export interface OfflineEvaluationCreateRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
  eval_set_id: string;
  target_type: string;
  target_id: string;
  experiment_id?: string | null;
}

export interface OnlineValidationCreateRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
  deployment_id: string;
  experiment_id?: string | null;
}

export interface ExperimentCreateRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
}

export interface ModelDeploymentCreateRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
  source_type: string;
  source_id: string;
  experiment_id?: string | null;
}

export type EvaluationDatasetListResponse = PagedResponse<EvaluationDataset>;
export type EvaluationDatasetItemListResponse = PagedResponse<EvaluationDatasetItem>;
export type TrainingJobListResponse = PagedResponse<TrainingJob>;
export type FineTuneRunListResponse = PagedResponse<FineTuneRun>;
export type OfflineEvaluationListResponse = PagedResponse<OfflineEvaluation>;
export type OnlineValidationListResponse = PagedResponse<OnlineValidation>;
export type ExperimentListResponse = PagedResponse<Experiment>;
export type DeploymentListResponse = PagedResponse<Deployment>;
