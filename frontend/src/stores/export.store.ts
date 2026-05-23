import { defineStore } from "pinia";
import { ref } from "vue";
import { exportApi } from "@/api/export.api";
import type {
  ExportJob,
  ExportJobCreatePayload,
  ExportJobQuery,
} from "@/types/governance.types";

export const useExportStore = defineStore("export", () => {
  const jobs = ref<ExportJob[]>([]);
  const total = ref(0);
  const loading = ref(false);

  async function fetchJobs(query: ExportJobQuery) {
    loading.value = true;
    try {
      const { data } = await exportApi.list(query);
      jobs.value = data.data.items;
      total.value = data.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function createJob(payload: ExportJobCreatePayload) {
    const { data } = await exportApi.create(payload);
    jobs.value.unshift(data.data);
    return data.data;
  }

  async function removeJob(id: string) {
    await exportApi.remove(id);
    jobs.value = jobs.value.filter((j) => j.id !== id);
  }

  return { jobs, total, loading, fetchJobs, createJob, removeJob };
});
