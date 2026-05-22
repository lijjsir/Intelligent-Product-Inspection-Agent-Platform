import { http } from "./http";
import type {
  AlgoListQuery,
  AlgoResourceActionResponse,
  AlignmentPair,
  DatasetProcessingResults,
  DatasetProcessingRunRequest,
  DatasetProcessingStatus,
  DatasetProcessingSubgraph,
  DatasetProcessingType,
  AugmentationProposal,
  Deployment,
  DeploymentListResponse,
  EvaluationDataset,
  EvaluationDatasetCreateRequest,
  EvaluationDatasetItemListQuery,
  EvaluationDatasetItemListResponse,
  EvaluationDatasetListResponse,
  EvaluationDatasetSampleAppendRequest,
  EvaluationDatasetUpdateRequest,
  Experiment,
  ExperimentCreateRequest,
  ExperimentListResponse,
  FineTuneRun,
  FineTuneRunCreateRequest,
  FineTuneRunListResponse,
  FineTuneRunUpdateRequest,
  KnowledgeGraphEntity,
  KnowledgeGraphRelation,
  ModelDeploymentCreateRequest,
  OfflineEvaluation,
  OfflineEvaluationCreateRequest,
  OfflineEvaluationListResponse,
  OfflineEvaluationUpdateRequest,
  OnlineValidation,
  OnlineValidationCreateRequest,
  OnlineValidationListResponse,
  TrainingJob,
  TrainingJobCreateRequest,
  TrainingJobListResponse,
  TrainingJobUpdateRequest,
} from "@/types/algo-workspace.types";

const processingBase = (datasetId: string, type: DatasetProcessingType) =>
  type === "export" ? `/v1/datasets/${datasetId}/exports` : `/v1/datasets/${datasetId}/processing/${type}`;

export const algoWorkspaceApi = {
  startProcessing(datasetId: string, type: DatasetProcessingType, payload: DatasetProcessingRunRequest) {
    const url = type === "export" ? processingBase(datasetId, type) : `${processingBase(datasetId, type)}/start`;
    return http.post<DatasetProcessingStatus | EvaluationDataset>(url, payload);
  },

  getProcessingStatus(datasetId: string, type: DatasetProcessingType) {
    const url = type === "export" ? `${processingBase(datasetId, type)}/status` : `${processingBase(datasetId, type)}/status`;
    return http.get<DatasetProcessingStatus>(url);
  },

  getProcessingResults(datasetId: string, type: DatasetProcessingType) {
    const url = type === "export" ? `${processingBase(datasetId, type)}/results` : `${processingBase(datasetId, type)}/results`;
    return http.get<DatasetProcessingResults>(url);
  },

  getKgSubgraph(datasetId: string, payload: { entity_type?: string; keyword?: string }) {
    return http.post<DatasetProcessingSubgraph>(`/v1/datasets/${datasetId}/processing/kg/subgraph`, payload);
  },

  createKgEntity(datasetId: string, payload: Partial<KnowledgeGraphEntity> & { name: string; entity_type: string }) {
    return http.post<KnowledgeGraphEntity>(`/v1/datasets/${datasetId}/processing/kg/entities`, payload);
  },

  deleteKgEntity(datasetId: string, entityId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/datasets/${datasetId}/processing/kg/entities/${entityId}`);
  },

  createKgRelation(datasetId: string, payload: Partial<KnowledgeGraphRelation> & { source_entity_id: string; target_entity_id: string; relation_type: string }) {
    return http.post<KnowledgeGraphRelation>(`/v1/datasets/${datasetId}/processing/kg/relations`, payload);
  },

  deleteKgRelation(datasetId: string, relationId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/datasets/${datasetId}/processing/kg/relations/${relationId}`);
  },

  createAlignmentPair(datasetId: string, payload: Partial<AlignmentPair>) {
    return http.post<AlignmentPair>(`/v1/datasets/${datasetId}/processing/alignment/pairs`, payload);
  },

  confirmAlignmentPair(datasetId: string, pairId: string) {
    return http.post<AlignmentPair>(`/v1/datasets/${datasetId}/processing/alignment/pairs/${pairId}/confirm`);
  },

  deleteAlignmentPair(datasetId: string, pairId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/datasets/${datasetId}/processing/alignment/pairs/${pairId}`);
  },

  createAugmentationProposal(datasetId: string, payload: Partial<AugmentationProposal> & { name: string }) {
    return http.post<AugmentationProposal>(`/v1/datasets/${datasetId}/processing/augmentation/proposals`, payload);
  },

  deleteAugmentationProposal(datasetId: string, proposalId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/datasets/${datasetId}/processing/augmentation/proposals/${proposalId}`);
  },

  applyAugmentation(datasetId: string, payload: { proposal_ids: string[] }) {
    return http.post<{ created_sample_ids: string[]; proposal_ids: string[] }>(`/v1/datasets/${datasetId}/processing/augmentation/apply`, payload);
  },

  getAugmentationHistory(datasetId: string) {
    return http.get<{ batch_id: string; history: AugmentationProposal[] }>(`/v1/datasets/${datasetId}/processing/augmentation/history`);
  },

  listEvalDatasets(query: AlgoListQuery) {
    return http.get<EvaluationDatasetListResponse>("/v1/eval-datasets", { params: query });
  },

  getEvalDataset(id: string) {
    return http.get<EvaluationDataset>(`/v1/eval-datasets/${id}`);
  },

  listEvalDatasetSamples(id: string, query: EvaluationDatasetItemListQuery) {
    return http.get<EvaluationDatasetItemListResponse>(`/v1/eval-datasets/${id}/samples`, { params: query });
  },

  appendEvalDatasetSamples(id: string, payload: EvaluationDatasetSampleAppendRequest) {
    return http.post<EvaluationDataset>(`/v1/eval-datasets/${id}/samples`, payload);
  },

  removeEvalDatasetSample(id: string, itemId: string) {
    return http.delete<{ deleted: boolean }>(`/v1/eval-datasets/${id}/samples/${itemId}`);
  },

  createEvalDataset(payload: EvaluationDatasetCreateRequest) {
    return http.post<EvaluationDataset>("/v1/eval-datasets", payload);
  },

  updateEvalDataset(id: string, payload: EvaluationDatasetUpdateRequest) {
    return http.patch<EvaluationDataset>(`/v1/eval-datasets/${id}`, payload);
  },

  removeEvalDataset(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/eval-datasets/${id}`);
  },

  listTrainingJobs(query: AlgoListQuery) {
    return http.get<TrainingJobListResponse>("/v1/training-jobs", { params: query });
  },

  getTrainingJob(id: string) {
    return http.get<TrainingJob>(`/v1/training-jobs/${id}`);
  },

  createTrainingJob(payload: TrainingJobCreateRequest) {
    return http.post<TrainingJob>("/v1/training-jobs", payload);
  },

  updateTrainingJob(id: string, payload: TrainingJobUpdateRequest) {
    return http.patch<TrainingJob>(`/v1/training-jobs/${id}`, payload);
  },

  launchTrainingJob(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/training-jobs/${id}/launch`);
  },

  cancelTrainingJob(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/training-jobs/${id}/cancel`);
  },

  removeTrainingJob(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/training-jobs/${id}`);
  },

  listFineTunes(query: AlgoListQuery) {
    return http.get<FineTuneRunListResponse>("/v1/fine-tunes", { params: query });
  },

  getFineTune(id: string) {
    return http.get<FineTuneRun>(`/v1/fine-tunes/${id}`);
  },

  createFineTune(payload: FineTuneRunCreateRequest) {
    return http.post<FineTuneRun>("/v1/fine-tunes", payload);
  },

  updateFineTune(id: string, payload: FineTuneRunUpdateRequest) {
    return http.patch<FineTuneRun>(`/v1/fine-tunes/${id}`, payload);
  },

  launchFineTune(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/fine-tunes/${id}/launch`);
  },

  cancelFineTune(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/fine-tunes/${id}/cancel`);
  },

  removeFineTune(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/fine-tunes/${id}`);
  },

  listOfflineEvaluations(query: AlgoListQuery) {
    return http.get<OfflineEvaluationListResponse>("/v1/offline-evaluations", { params: query });
  },

  getOfflineEvaluation(id: string) {
    return http.get<OfflineEvaluation>(`/v1/offline-evaluations/${id}`);
  },

  createOfflineEvaluation(payload: OfflineEvaluationCreateRequest) {
    return http.post<OfflineEvaluation>("/v1/offline-evaluations", payload);
  },

  updateOfflineEvaluation(id: string, payload: OfflineEvaluationUpdateRequest) {
    return http.patch<OfflineEvaluation>(`/v1/offline-evaluations/${id}`, payload);
  },

  launchOfflineEvaluation(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/offline-evaluations/${id}/launch`);
  },

  cancelOfflineEvaluation(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/offline-evaluations/${id}/cancel`);
  },

  removeOfflineEvaluation(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/offline-evaluations/${id}`);
  },

  listOnlineValidations(query: AlgoListQuery) {
    return http.get<OnlineValidationListResponse>("/v1/online-validations", { params: query });
  },

  getOnlineValidation(id: string) {
    return http.get<OnlineValidation>(`/v1/online-validations/${id}`);
  },

  createOnlineValidation(payload: OnlineValidationCreateRequest) {
    return http.post<OnlineValidation>("/v1/online-validations", payload);
  },

  updateOnlineValidation(id: string, payload: Record<string, unknown>) {
    return http.patch<OnlineValidation>(`/v1/online-validations/${id}`, payload);
  },

  launchOnlineValidation(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/online-validations/${id}/launch`);
  },

  cancelOnlineValidation(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/online-validations/${id}/cancel`);
  },

  removeOnlineValidation(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/online-validations/${id}`);
  },

  listExperiments(query: AlgoListQuery) {
    return http.get<ExperimentListResponse>("/v1/experiments", { params: query });
  },

  getExperiment(id: string) {
    return http.get<Experiment>(`/v1/experiments/${id}`);
  },

  createExperiment(payload: ExperimentCreateRequest) {
    return http.post<Experiment>("/v1/experiments", payload);
  },

  updateExperiment(id: string, payload: Record<string, unknown>) {
    return http.patch<Experiment>(`/v1/experiments/${id}`, payload);
  },

  removeExperiment(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/experiments/${id}`);
  },

  listDeployments(query: AlgoListQuery) {
    return http.get<DeploymentListResponse>("/v1/deployments", { params: query });
  },

  getDeployment(id: string) {
    return http.get<Deployment>(`/v1/deployments/${id}`);
  },

  createDeployment(payload: ModelDeploymentCreateRequest) {
    return http.post<Deployment>("/v1/deployments", payload);
  },

  updateDeployment(id: string, payload: Record<string, unknown>) {
    return http.patch<Deployment>(`/v1/deployments/${id}`, payload);
  },

  launchDeployment(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/deployments/${id}/launch`);
  },

  cancelDeployment(id: string) {
    return http.post<AlgoResourceActionResponse>(`/v1/deployments/${id}/cancel`);
  },

  removeDeployment(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/deployments/${id}`);
  },
};
