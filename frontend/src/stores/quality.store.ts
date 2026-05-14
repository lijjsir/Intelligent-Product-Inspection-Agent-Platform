import { defineStore } from "pinia";
import { ref } from "vue";
import { qualityApi } from "@/api/quality.api";
import type { QualityReport, QualityTraceItem } from "@/types/governance.types";

export const useQualityStore = defineStore("quality", () => {
  const report = ref<QualityReport | null>(null);
  const traces = ref<QualityTraceItem[]>([]);
  const loading = ref(false);

  async function fetchReport(params?: { start_date?: string; end_date?: string; source?: "all" | "inspection" | "chat" }) {
    loading.value = true;
    try {
      const { data } = await qualityApi.getReport(params);
      report.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchTraces(params?: { source?: "all" | "inspection" | "chat"; limit?: number }) {
    loading.value = true;
    try {
      const { data } = await qualityApi.listTraces(params);
      traces.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  return { report, traces, loading, fetchReport, fetchTraces };
});

