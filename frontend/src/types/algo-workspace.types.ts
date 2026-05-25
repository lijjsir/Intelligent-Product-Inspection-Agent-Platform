import type { PageParams, PagedResponse } from "./common.types";
import type { DatasetSampleType } from "./dataset.types";

export type AlgoResourceStatus = "draft" | "queued" | "running" | "completed" | "failed" | "cancelled";
export type AlgoExecutionMode = "local_background" | "celery" | "gpu_ssh";
export type DatasetProcessingType = "kg" | "alignment" | "augmentation" | "export";
export type DatasetExportFormat = "vlm-json" | "coco" | "yolo";

export interface DatasetExportRequest {
  name: string;
  description?: string;
  format?: DatasetExportFormat;
  train_ratio?: number;
  val_ratio?: number;
  test_ratio?: number;
  include_augmented?: boolean;
  only_confirmed_alignment?: boolean;
}

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
  execution_mode?: AlgoExecutionMode | string | null;
  executor_job_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface GpuLeaseSummary {
  node_ids: string[];
  gpu_indices_by_node: Record<string, number[]>;
  leased_at?: string | null;
  released_at?: string | null;
}

export interface RemoteExecutionSummary {
  host?: string | null;
  workdir?: string | null;
  command_preview?: string | null;
  remote_pid?: string | null;
  log_path?: string | null;
  status_path?: string | null;
  service_pid_path?: string | null;
  exit_code?: number | null;
  last_polled_at?: string | null;
  last_remote_status?: string | null;
  last_log_tail?: string | null;
  poll_error?: string | null;
  status_file_state?: string | null;
  poll_fail_count?: number | null;
}

export interface RuntimeRegistrationSummary {
  source_type?: string;
  source_id?: string;
  model_key?: string | null;
  provider?: string | null;
  endpoint?: string | null;
  health_url?: string | null;
  infer_url?: string | null;
  model_version?: string | null;
  service_status?: string | null;
  remote_pid?: string | null;
  available_at?: string | null;
  last_checked_at?: string | null;
  last_health_checked_at?: string | null;
  last_health_error?: string | null;
  leased_node_ids?: string[];
  gpu_indices_by_node?: Record<string, number[]>;
  inference_config?: Record<string, unknown>;
  request_timeout_ms?: number | null;
  service_port?: number | null;
}

export interface TrainingExecutionSummary {
  status?: string;
  execution_mode?: AlgoExecutionMode | string | null;
  started_at?: string | null;
  completed_at?: string | null;
  source_dataset_id?: string;
  eval_set_id?: string | null;
  model_config_id?: string | null;
  model_key?: string | null;
  effective_hyperparameters?: Record<string, unknown>;
  base_model_ref?: Record<string, unknown>;
  lora?: Record<string, unknown>;
  lease?: GpuLeaseSummary;
  remote_execution?: RemoteExecutionSummary;
}

export interface TrainingArtifact {
  type: string;
  name?: string;
  path?: string;
  [key: string]: unknown;
}

export interface SummaryHighlightItem {
  label: string;
  value: unknown;
  unit?: string;
  tone?: "primary" | "success" | "warning" | "danger" | "info";
  hint?: string;
}

export interface SummaryArtifactItem {
  title: string;
  subtitle?: string;
  meta?: Record<string, unknown> | null;
  path?: string | null;
  type?: string | null;
  link?: string | null;
}

export interface SummaryLogItem {
  text: string;
  level?: string | null;
  timestamp?: string | null;
}

export interface SummaryMetricItem {
  key: string;
  label: string;
  value: unknown;
}

export interface TrainingMetrics {
  train_loss?: number[];
  val_accuracy?: number[];
  summary?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface TrainingResultSummary {
  summary?: TrainingExecutionSummary;
  artifacts: TrainingArtifact[];
  metrics: TrainingMetrics;
  logs: string[];
  lease?: GpuLeaseSummary;
  remote_execution?: RemoteExecutionSummary;
}
export type TrainingResultSummaryRecord = TrainingResultSummary & Record<string, unknown>;

export interface OfflineEvaluationResultSummary {
  summary?: {
    status?: string;
    execution_mode?: AlgoExecutionMode | string | null;
    started_at?: string | null;
    completed_at?: string | null;
    eval_set_id?: string;
    target_type?: string;
    target_id?: string;
    lease?: GpuLeaseSummary;
    remote_execution?: RemoteExecutionSummary;
  };
  metrics: Record<string, unknown>;
  error_cases: Array<Record<string, unknown>>;
  artifacts: TrainingArtifact[];
  logs: string[];
  lease?: GpuLeaseSummary;
  remote_execution?: RemoteExecutionSummary;
}
export type OfflineEvaluationResultSummaryRecord = OfflineEvaluationResultSummary & Record<string, unknown>;

export interface OnlineValidationMetrics {
  shadow_pass_rate?: number;
  avg_latency_ms?: number;
  throughput_qps?: number;
  replay_count?: number;
  baseline_runtime_status?: string;
  error_count?: number;
  [key: string]: unknown;
}

export interface OnlineValidationReplaySample {
  task_id?: string;
  product_id?: string;
  spec_code?: string;
  verdict?: string | null;
  overall_score?: number | null;
}

export interface OnlineValidationResultSummary {
  summary?: {
    status?: string;
    execution_mode?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    deployment_id?: string;
    validation_type?: string;
    replay_source?: string;
    replay_count?: number;
  };
  metrics: OnlineValidationMetrics;
  replay_samples?: OnlineValidationReplaySample[];
  failure_samples?: Array<Record<string, unknown>>;
  artifacts: TrainingArtifact[];
  logs: string[];
}
export type OnlineValidationResultSummaryRecord = OnlineValidationResultSummary & Record<string, unknown>;

export interface DeploymentResultSummary {
  summary?: {
    status?: string;
    execution_mode?: AlgoExecutionMode | string | null;
    started_at?: string | null;
    completed_at?: string | null;
    source_type?: string;
    source_id?: string;
    merge_mode?: "dynamic" | "static";
    lease?: GpuLeaseSummary;
    remote_execution?: RemoteExecutionSummary;
  };
  runtime_registration: RuntimeRegistrationSummary;
  artifacts: TrainingArtifact[];
  logs: string[];
  lease?: GpuLeaseSummary;
  remote_execution?: RemoteExecutionSummary;
}
export type DeploymentResultSummaryRecord = DeploymentResultSummary & Record<string, unknown>;

export interface AlgoDeploymentInferResult {
  deployment_id: string;
  deployment_status: string;
  runtime_status: string;
  prediction: unknown;
  latency_ms?: number | null;
  model_version?: string | null;
  request_id?: string | null;
  error?: string | null;
  runtime_registration?: RuntimeRegistrationSummary;
  accepted_at: string;
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
  created_sample_id?: string | null;
  created_sample_ids?: string[];
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
  source_dataset_name?: string | null;
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

export interface FineTuneRun extends AlgoExecutionResource {
  source_dataset_id: string;
  source_dataset_name?: string | null;
  model_config_id: string;
  model_config_ref?: ResourceModelRef | null;
  eval_set_id?: string | null;
  eval_set_name?: string | null;
  experiment_id?: string | null;
  experiment_name?: string | null;
  result_summary?: TrainingResultSummaryRecord | null;
}

export interface OfflineEvaluation extends AlgoExecutionResource {
  eval_set_id: string;
  eval_set_name?: string | null;
  target_type: string;
  target_id: string;
  target_name?: string | null;
  experiment_id?: string | null;
  experiment_name?: string | null;
  result_summary?: OfflineEvaluationResultSummaryRecord | null;
}

export interface OnlineValidation extends AlgoExecutionResource {
  deployment_id: string;
  deployment_name?: string | null;
  experiment_id?: string | null;
  experiment_name?: string | null;
  result_summary?: OnlineValidationResultSummaryRecord | null;
}

export interface ExperimentRelatedResourceSummary {
  id: string;
  name: string;
  status: AlgoResourceStatus;
  metrics: Record<string, unknown>;
  updated_at?: string | null;
}

export interface Experiment extends AlgoResourceBase {
  related_resources?: {
    fine_tunes: ExperimentRelatedResourceSummary[];
    offline_evaluations: ExperimentRelatedResourceSummary[];
    deployments: ExperimentRelatedResourceSummary[];
  };
}

export interface Deployment extends AlgoExecutionResource {
  source_type: "training_job" | "fine_tune";
  source_id: string;
  source_name?: string | null;
  merge_mode: "dynamic" | "static";
  experiment_id?: string | null;
  experiment_name?: string | null;
  result_summary?: DeploymentResultSummaryRecord | null;
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

export interface FineTuneRunCreateRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
  source_dataset_id: string;
  model_config_id: string;
  eval_set_id?: string | null;
  experiment_id?: string | null;
}

export interface FineTuneRunUpdateRequest {
  name?: string;
  description?: string | null;
  config_json?: Record<string, unknown>;
  source_dataset_id?: string | null;
  model_config_id?: string | null;
  eval_set_id?: string | null;
  experiment_id?: string | null;
}

export interface OfflineEvaluationCreateRequest {
  name: string;
  description?: string;
  config_json?: Record<string, unknown>;
  eval_set_id: string;
  target_type: "training_job" | "fine_tune" | "deployment";
  target_id: string;
  experiment_id?: string | null;
}

export interface OfflineEvaluationUpdateRequest {
  name?: string;
  description?: string | null;
  config_json?: Record<string, unknown>;
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
  source_type: "training_job" | "fine_tune";
  source_id: string;
  merge_mode?: "dynamic" | "static";
  experiment_id?: string | null;
}

export type EvaluationDatasetListResponse = PagedResponse<EvaluationDataset>;
export type EvaluationDatasetItemListResponse = PagedResponse<EvaluationDatasetItem>;
export type FineTuneRunListResponse = PagedResponse<FineTuneRun>;
export type OfflineEvaluationListResponse = PagedResponse<OfflineEvaluation>;
export type OnlineValidationListResponse = PagedResponse<OnlineValidation>;
export type ExperimentListResponse = PagedResponse<Experiment>;
export type DeploymentListResponse = PagedResponse<Deployment>;
