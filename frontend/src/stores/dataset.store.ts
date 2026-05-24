import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { datasetApi } from "@/api/dataset.api";
import type {
  Dataset,
  DatasetCreateRequest,
  DatasetDetail,
  DatasetListQuery,
  DatasetSample,
  DatasetSampleCreateRequest,
  DatasetSampleListQuery,
  DatasetUpdateRequest,
} from "@/types/dataset.types";

export const useDatasetStore = defineStore("dataset", () => {
  const items = ref<Dataset[]>([]);
  const current = ref<DatasetDetail | null>(null);
  const samples = ref<DatasetSample[]>([]);
  const total = ref(0);
  const sampleTotal = ref(0);
  const loading = ref(false);
  const sampleLoading = ref(false);

  const count = computed(() => items.value.length);

  async function fetchDatasets(query: DatasetListQuery) {
    loading.value = true;
    try {
      const { data } = await datasetApi.list(query);
      items.value = data.data.items;
      total.value = data.data.total;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchDataset(id: string) {
    loading.value = true;
    try {
      const { data } = await datasetApi.get(id);
      current.value = data.data;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function createDataset(payload: DatasetCreateRequest) {
    const { data } = await datasetApi.create(payload);
    items.value.unshift(data.data);
    total.value += 1;
    return data.data;
  }

  async function updateDataset(id: string, payload: DatasetUpdateRequest) {
    const { data } = await datasetApi.update(id, payload);
    const index = items.value.findIndex((item) => item.id === id);
    if (index !== -1) {
      items.value[index] = data.data;
    }
    if (current.value?.id === id) {
      current.value = data.data;
    }
    return data.data;
  }

  async function removeDataset(id: string) {
    await datasetApi.remove(id);
    items.value = items.value.filter((item) => item.id !== id);
    total.value = Math.max(0, total.value - 1);
    if (current.value?.id === id) {
      current.value = null;
    }
  }

  async function fetchSamples(datasetId: string, query: DatasetSampleListQuery) {
    sampleLoading.value = true;
    try {
      const { data } = await datasetApi.listSamples(datasetId, query);
      samples.value = data.data.items;
      sampleTotal.value = data.data.total;
      return data.data;
    } finally {
      sampleLoading.value = false;
    }
  }

  async function createTextSample(datasetId: string, payload: DatasetSampleCreateRequest) {
    const { data } = await datasetApi.createTextSample(datasetId, payload);
    return data.data;
  }

  async function uploadImageSamples(datasetId: string, files: File[]) {
    const { data } = await datasetApi.uploadImageSamples(datasetId, files);
    return data.data;
  }

  async function uploadVideoSamples(datasetId: string, files: File[]) {
    const { data } = await datasetApi.uploadVideoSamples(datasetId, files);
    return data.data;
  }

  async function removeSample(datasetId: string, sampleId: string) {
    await datasetApi.removeSample(datasetId, sampleId);
    samples.value = samples.value.filter((item) => item.id !== sampleId);
    sampleTotal.value = Math.max(0, sampleTotal.value - 1);
  }

  function $reset() {
    items.value = [];
    current.value = null;
    samples.value = [];
    total.value = 0;
    sampleTotal.value = 0;
  }

  return {
    items,
    current,
    samples,
    total,
    sampleTotal,
    loading,
    sampleLoading,
    count,
    fetchDatasets,
    fetchDataset,
    createDataset,
    updateDataset,
    removeDataset,
    fetchSamples,
    createTextSample,
    uploadImageSamples,
    uploadVideoSamples,
    removeSample,
    $reset,
  };
});
