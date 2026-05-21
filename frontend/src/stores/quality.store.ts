import { defineStore } from "pinia";
import { ref } from "vue";
import { qualityApi } from "@/api/quality.api";
import type { QualityReport, QualityTraceDeleteResult, QualityTraceItem, QualityTraceMeta } from "@/types/governance.types";

export const useQualityStore = defineStore("quality", () => {
  const report = ref<QualityReport | null>(null);
  const traces = ref<QualityTraceItem[]>([]);
  const traceMeta = ref<QualityTraceMeta | null>(null);
  const loading = ref(false);

  async function fetchReport(params?: { start_date?: string; end_date?: string; source?: "all" | "inspection" | "chat" }) {
    loading.value = true;
    try {
      const { data } = await qualityApi.getReport(params);
      report.value = data.data;
      return report.value;
    } finally {
      loading.value = false;
    }
  }

  async function fetchTraces(params?: { source?: "all" | "inspection" | "chat"; limit?: number }) {
    loading.value = true;
    try {
      const { data } = await qualityApi.listTraces(params);
      traces.value = data.data?.items ?? [];
      traceMeta.value = data.data?.meta ?? null;
      return { items: traces.value, meta: traceMeta.value };
    } finally {
      loading.value = false;
    }
  }

  async function deleteTrace(traceId: string): Promise<QualityTraceDeleteResult> {
    const { data } = await qualityApi.deleteTrace(traceId);
    const result = data.data;
    if (result?.deleted) {
      traces.value = traces.value.filter((t) => t.trace_id !== traceId);
    }
    return result;
  }

  return { report, traces, traceMeta, loading, fetchReport, fetchTraces, deleteTrace };
});
