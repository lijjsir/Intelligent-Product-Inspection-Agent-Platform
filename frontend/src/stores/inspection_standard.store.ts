import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { inspectionStandardApi } from "@/api/inspection-standard.api";
import type {
  InspectionStandardLibraryItem,
  InspectionStandardPayload,
  InspectionStandardQuery,
  StandardDocumentItem,
  StandardLibraryIndexResult,
  StandardLibraryScanResult,
  StandardRetrievePayload,
  StandardRetrieveResult,
} from "@/types/governance.types";

export const useInspectionStandardStore = defineStore("inspection-standard-library", () => {
  const items = ref<InspectionStandardLibraryItem[]>([]);
  const documents = ref<StandardDocumentItem[]>([]);
  const loading = ref(false);
  const documentLoading = ref(false);
  const actionLoading = ref("");
  const count = computed(() => items.value.length);
  const metrics = computed(() => ({
    libraries: items.value.length,
    pdfs: items.value.reduce((sum, item) => sum + Number(item.pdf_count || 0), 0),
    chunks: items.value.reduce((sum, item) => sum + Number(item.chunk_count || 0), 0),
    failed: items.value.filter((item) => ["failed", "partial_failed"].includes(item.import_status)).length,
  }));

  async function fetchAll(params?: InspectionStandardQuery) {
    loading.value = true;
    try {
      const { data } = await inspectionStandardApi.list(params);
      items.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  async function createOne(payload: InspectionStandardPayload) {
    const { data } = await inspectionStandardApi.create(payload);
    items.value.unshift(data.data);
    return data.data;
  }

  async function updateOne(id: string, payload: Partial<InspectionStandardPayload>) {
    const { data } = await inspectionStandardApi.update(id, payload);
    const index = items.value.findIndex((item) => item.id === id);
    if (index !== -1) items.value[index] = data.data;
    return data.data;
  }

  async function removeOne(id: string) {
    await inspectionStandardApi.remove(id);
    items.value = items.value.filter((item) => item.id !== id);
  }

  async function scanOne(id: string): Promise<StandardLibraryScanResult> {
    actionLoading.value = `scan:${id}`;
    try {
      const { data } = await inspectionStandardApi.scan(id);
      await fetchAll();
      return data.data;
    } finally {
      actionLoading.value = "";
    }
  }

  async function indexOne(id: string, reindex = false): Promise<StandardLibraryIndexResult> {
    actionLoading.value = `${reindex ? "reindex" : "index"}:${id}`;
    try {
      const { data } = reindex ? await inspectionStandardApi.reindex(id) : await inspectionStandardApi.index(id);
      await fetchAll();
      return data.data;
    } finally {
      actionLoading.value = "";
    }
  }

  async function fetchDocuments(id: string) {
    documentLoading.value = true;
    try {
      const { data } = await inspectionStandardApi.listDocuments(id);
      documents.value = data.data;
      return data.data;
    } finally {
      documentLoading.value = false;
    }
  }

  async function retrieve(payload: StandardRetrievePayload): Promise<StandardRetrieveResult> {
    const { data } = await inspectionStandardApi.retrieve(payload);
    return data.data;
  }

  function $reset() {
    items.value = [];
    documents.value = [];
    actionLoading.value = "";
  }

  return {
    items,
    documents,
    loading,
    documentLoading,
    actionLoading,
    count,
    metrics,
    fetchAll,
    createOne,
    updateOne,
    removeOne,
    scanOne,
    indexOne,
    fetchDocuments,
    retrieve,
    $reset,
  };
});
