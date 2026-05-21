import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { algoWorkspaceApi } from "@/api/algo-workspace.api";
import type {
  AlignmentPair,
  AugmentationProposal,
  DatasetProcessingResults,
  DatasetProcessingRunRequest,
  DatasetProcessingStatus,
  DatasetProcessingSubgraph,
  DatasetProcessingType,
  KnowledgeGraphEntity,
  KnowledgeGraphRelation,
} from "@/types/algo-workspace.types";

export const useDatasetProcessingStore = defineStore("datasetProcessing", () => {
  const selectedDatasetId = ref("");
  const currentTab = ref<DatasetProcessingType>("kg");
  const statusMap = ref<Record<DatasetProcessingType, DatasetProcessingStatus | null>>({
    kg: null,
    alignment: null,
    augmentation: null,
    export: null,
  });
  const resultsMap = ref<Record<DatasetProcessingType, DatasetProcessingResults | null>>({
    kg: null,
    alignment: null,
    augmentation: null,
    export: null,
  });
  const loading = ref(false);
  const polling = ref(false);

  const activeStatus = computed(() => statusMap.value[currentTab.value]);
  const activeResults = computed(() => resultsMap.value[currentTab.value]);

  async function startProcessing(datasetId: string, type: DatasetProcessingType, payload: DatasetProcessingRunRequest) {
    selectedDatasetId.value = datasetId;
    loading.value = true;
    try {
      const { data } = await algoWorkspaceApi.startProcessing(datasetId, type, payload);
      statusMap.value[type] = data.data as DatasetProcessingStatus;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchStatus(datasetId: string, type: DatasetProcessingType) {
    selectedDatasetId.value = datasetId;
    const { data } = await algoWorkspaceApi.getProcessingStatus(datasetId, type);
    statusMap.value[type] = data.data;
    return data.data;
  }

  async function fetchResults(datasetId: string, type: DatasetProcessingType) {
    selectedDatasetId.value = datasetId;
    const { data } = await algoWorkspaceApi.getProcessingResults(datasetId, type);
    resultsMap.value[type] = data.data;
    return data.data;
  }

  async function refreshActive(datasetId: string, type: DatasetProcessingType) {
    await Promise.all([fetchStatus(datasetId, type), fetchResults(datasetId, type)]);
  }

  async function pollUntilSettled(datasetId: string, type: DatasetProcessingType, maxRounds = 6) {
    polling.value = true;
    try {
      for (let index = 0; index < maxRounds; index += 1) {
        const status = await fetchStatus(datasetId, type);
        await fetchResults(datasetId, type);
        const current = status.resource?.status;
        if (!current || ["completed", "failed", "cancelled"].includes(current)) {
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 250));
      }
    } finally {
      polling.value = false;
    }
  }

  async function createKgEntity(datasetId: string, payload: { name: string; entity_type: string; description?: string; properties_json?: Record<string, unknown> }) {
    const { data } = await algoWorkspaceApi.createKgEntity(datasetId, payload);
    await fetchResults(datasetId, "kg");
    return data.data as KnowledgeGraphEntity;
  }

  async function removeKgEntity(datasetId: string, entityId: string) {
    await algoWorkspaceApi.deleteKgEntity(datasetId, entityId);
    await fetchResults(datasetId, "kg");
  }

  async function createKgRelation(datasetId: string, payload: { source_entity_id: string; target_entity_id: string; relation_type: string; properties_json?: Record<string, unknown> }) {
    const { data } = await algoWorkspaceApi.createKgRelation(datasetId, payload);
    await fetchResults(datasetId, "kg");
    return data.data as KnowledgeGraphRelation;
  }

  async function removeKgRelation(datasetId: string, relationId: string) {
    await algoWorkspaceApi.deleteKgRelation(datasetId, relationId);
    await fetchResults(datasetId, "kg");
  }

  async function createAlignmentPair(datasetId: string, payload: { source_sample_id?: string; target_sample_id?: string; relation_type: string; similarity_score?: number }) {
    const { data } = await algoWorkspaceApi.createAlignmentPair(datasetId, payload);
    await fetchResults(datasetId, "alignment");
    return data.data as AlignmentPair;
  }

  async function confirmAlignmentPair(datasetId: string, pairId: string) {
    const { data } = await algoWorkspaceApi.confirmAlignmentPair(datasetId, pairId);
    await fetchResults(datasetId, "alignment");
    return data.data as AlignmentPair;
  }

  async function removeAlignmentPair(datasetId: string, pairId: string) {
    await algoWorkspaceApi.deleteAlignmentPair(datasetId, pairId);
    await fetchResults(datasetId, "alignment");
  }

  async function createAugmentationProposal(datasetId: string, payload: { name: string; description?: string; config_json?: Record<string, unknown>; result_summary?: Record<string, unknown> }) {
    const { data } = await algoWorkspaceApi.createAugmentationProposal(datasetId, payload);
    await fetchResults(datasetId, "augmentation");
    return data.data as AugmentationProposal;
  }

  async function applyAugmentation(datasetId: string, proposalIds: string[]) {
    const { data } = await algoWorkspaceApi.applyAugmentation(datasetId, { proposal_ids: proposalIds });
    await fetchResults(datasetId, "augmentation");
    return data.data;
  }

  async function getAugmentationHistory(datasetId: string) {
    const { data } = await algoWorkspaceApi.getAugmentationHistory(datasetId);
    return data.data;
  }

  async function getKgSubgraph(datasetId: string, payload: { entity_type?: string; keyword?: string }): Promise<DatasetProcessingSubgraph> {
    const { data } = await algoWorkspaceApi.getKgSubgraph(datasetId, payload);
    return data.data;
  }

  async function removeAugmentationProposal(datasetId: string, proposalId: string) {
    await algoWorkspaceApi.deleteAugmentationProposal(datasetId, proposalId);
    await fetchResults(datasetId, "augmentation");
  }

  return {
    selectedDatasetId,
    currentTab,
    statusMap,
    resultsMap,
    loading,
    polling,
    activeStatus,
    activeResults,
    startProcessing,
    fetchStatus,
    fetchResults,
    refreshActive,
    pollUntilSettled,
    createKgEntity,
    removeKgEntity,
    createKgRelation,
    removeKgRelation,
    createAlignmentPair,
    removeAlignmentPair,
    confirmAlignmentPair,
    createAugmentationProposal,
    removeAugmentationProposal,
    applyAugmentation,
    getAugmentationHistory,
    getKgSubgraph,
  };
});
