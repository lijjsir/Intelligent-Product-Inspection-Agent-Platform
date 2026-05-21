import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { algoWorkspaceApi } from "@/api/algo-workspace.api";
import type {
  AlgoListQuery,
  EvaluationDataset,
  EvaluationDatasetCreateRequest,
  EvaluationDatasetItem,
  EvaluationDatasetItemListQuery,
  EvaluationDatasetSampleAppendRequest,
  EvaluationDatasetUpdateRequest,
} from "@/types/algo-workspace.types";

export const useEvalDatasetStore = defineStore("evalDataset", () => {
  const items = ref<EvaluationDataset[]>([]);
  const current = ref<EvaluationDataset | null>(null);
  const detailItems = ref<EvaluationDatasetItem[]>([]);
  const total = ref(0);
  const detailTotal = ref(0);
  const loading = ref(false);
  const detailLoading = ref(false);
  const count = computed(() => items.value.length);

  async function fetchList(query: AlgoListQuery) {
    loading.value = true;
    try {
      const { data } = await algoWorkspaceApi.listEvalDatasets(query);
      items.value = data.data.items;
      total.value = data.data.total;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchOne(id: string) {
    loading.value = true;
    try {
      const { data } = await algoWorkspaceApi.getEvalDataset(id);
      current.value = data.data;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function createOne(payload: EvaluationDatasetCreateRequest) {
    const { data } = await algoWorkspaceApi.createEvalDataset(payload);
    items.value.unshift(data.data);
    total.value += 1;
    return data.data;
  }

  async function updateOne(id: string, payload: EvaluationDatasetUpdateRequest) {
    const { data } = await algoWorkspaceApi.updateEvalDataset(id, payload);
    const index = items.value.findIndex((item) => item.id === id);
    if (index !== -1) {
      items.value[index] = data.data;
    }
    if (current.value?.id === id) {
      current.value = data.data;
    }
    return data.data;
  }

  async function removeOne(id: string) {
    await algoWorkspaceApi.removeEvalDataset(id);
    items.value = items.value.filter((item) => item.id !== id);
    total.value = Math.max(0, total.value - 1);
    if (current.value?.id === id) {
      current.value = null;
      detailItems.value = [];
      detailTotal.value = 0;
    }
  }

  async function fetchSamples(id: string, query: EvaluationDatasetItemListQuery) {
    detailLoading.value = true;
    try {
      const { data } = await algoWorkspaceApi.listEvalDatasetSamples(id, query);
      detailItems.value = data.data.items;
      detailTotal.value = data.data.total;
      return data.data;
    } finally {
      detailLoading.value = false;
    }
  }

  async function appendSamples(id: string, payload: EvaluationDatasetSampleAppendRequest) {
    const { data } = await algoWorkspaceApi.appendEvalDatasetSamples(id, payload);
    current.value = data.data;
    const index = items.value.findIndex((item) => item.id === id);
    if (index !== -1) {
      items.value[index] = data.data;
    }
    return data.data;
  }

  async function removeSampleItem(id: string, itemId: string) {
    await algoWorkspaceApi.removeEvalDatasetSample(id, itemId);
    detailItems.value = detailItems.value.filter((item) => item.id !== itemId);
    detailTotal.value = Math.max(0, detailTotal.value - 1);
    if (current.value) {
      current.value = {
        ...current.value,
        sample_count: Math.max(0, current.value.sample_count - 1),
      };
    }
  }

  function $reset() {
    items.value = [];
    current.value = null;
    detailItems.value = [];
    total.value = 0;
    detailTotal.value = 0;
  }

  return {
    items,
    current,
    detailItems,
    total,
    detailTotal,
    loading,
    detailLoading,
    count,
    fetchList,
    fetchOne,
    createOne,
    updateOne,
    removeOne,
    fetchSamples,
    appendSamples,
    removeSampleItem,
    $reset,
  };
});
