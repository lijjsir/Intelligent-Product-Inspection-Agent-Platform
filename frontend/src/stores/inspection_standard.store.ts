import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { inspectionStandardApi } from "@/api/inspection-standard.api";
import type {
  InspectionStandardLibraryItem,
  InspectionStandardPayload,
  InspectionStandardQuery,
  StandardDocumentChunkItem,
  StandardDocumentItem,
  StandardDocumentPayload,
  StandardLibraryIndexResult,
  StandardLibraryScanResult,
  StandardRetrievePayload,
  StandardRetrieveResult,
  StandardUploadResult,
} from "@/types/governance.types";

export const useInspectionStandardStore = defineStore("inspection-standard-library", () => {
  const items = ref<InspectionStandardLibraryItem[]>([]);
  const documents = ref<StandardDocumentItem[]>([]);
  const chunks = ref<StandardDocumentChunkItem[]>([]);
  const loading = ref(false);
  const documentLoading = ref(false);
  const chunkLoading = ref(false);
  const actionLoading = ref("");

  // Pagination state
  const total = ref(0);
  const page = ref(1);
  const size = ref(50);
  const docTotal = ref(0);
  const docPage = ref(1);
  const docSize = ref(50);

  const count = computed(() => total.value);
  const metrics = computed(() => ({
    libraries: total.value,
    pdfs: items.value.reduce((sum, item) => sum + Number(item.pdf_count || 0), 0),
    chunks: items.value.reduce((sum, item) => sum + Number(item.chunk_count || 0), 0),
    failed: items.value.filter((item) => ["failed", "partial_failed"].includes(item.import_status)).length,
  }));

  async function fetchAll(params?: InspectionStandardQuery) {
    loading.value = true;
    try {
      const query = { page: page.value, size: size.value, ...params };
      const { data } = await inspectionStandardApi.list(query);
      items.value = data.data.items;
      total.value = data.data.total;
      page.value = data.data.page;
      size.value = data.data.size;
    } finally {
      loading.value = false;
    }
  }

  function setPage(newPage: number) {
    page.value = newPage;
    return fetchAll();
  }

  function setSize(newSize: number) {
    size.value = newSize;
    page.value = 1;
    return fetchAll();
  }

  async function createOne(payload: InspectionStandardPayload) {
    const { data } = await inspectionStandardApi.create(payload);
    await fetchAll();
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
    await fetchAll();
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

  async function uploadOne(id: string, files: File[]): Promise<StandardUploadResult> {
    actionLoading.value = `upload:${id}`;
    try {
      const { data } = await inspectionStandardApi.upload(id, files);
      await fetchAll();
      return data.data;
    } finally {
      actionLoading.value = "";
    }
  }

  async function fetchDocuments(libraryId: string, p?: { page?: number; size?: number }) {
    documentLoading.value = true;
    try {
      const params = { page: p?.page || docPage.value, size: p?.size || docSize.value };
      const { data } = await inspectionStandardApi.listDocuments(libraryId, params);
      documents.value = data.data.items;
      docTotal.value = data.data.total;
      docPage.value = data.data.page;
      docSize.value = data.data.size;
      return data.data;
    } finally {
      documentLoading.value = false;
    }
  }

  function setDocPage(newPage: number, libraryId: string) {
    docPage.value = newPage;
    return fetchDocuments(libraryId);
  }

  async function fetchChunks(documentId: string) {
    chunkLoading.value = true;
    try {
      const { data } = await inspectionStandardApi.listChunks(documentId);
      chunks.value = data.data;
      return data.data;
    } finally {
      chunkLoading.value = false;
    }
  }

  async function updateDocument(documentId: string, payload: StandardDocumentPayload) {
    const { data } = await inspectionStandardApi.updateDocument(documentId, payload);
    const index = documents.value.findIndex((d) => d.id === documentId);
    if (index !== -1) documents.value[index] = data.data;
    return data.data;
  }

  async function removeDocument(documentId: string) {
    await inspectionStandardApi.deleteDocument(documentId);
    documents.value = documents.value.filter((d) => d.id !== documentId);
  }

  async function retrieve(payload: StandardRetrievePayload): Promise<StandardRetrieveResult> {
    const { data } = await inspectionStandardApi.retrieve(payload);
    return data.data;
  }

  function $reset() {
    items.value = [];
    documents.value = [];
    chunks.value = [];
    actionLoading.value = "";
    total.value = 0;
    page.value = 1;
    docTotal.value = 0;
    docPage.value = 1;
  }

  return {
    items,
    documents,
    chunks,
    loading,
    documentLoading,
    chunkLoading,
    actionLoading,
    total,
    page,
    size,
    docTotal,
    docPage,
    docSize,
    count,
    metrics,
    fetchAll,
    setPage,
    setSize,
    createOne,
    updateOne,
    removeOne,
    scanOne,
    indexOne,
    uploadOne,
    fetchDocuments,
    setDocPage,
    fetchChunks,
    updateDocument,
    removeDocument,
    retrieve,
    $reset,
  };
});
