import { defineStore } from "pinia";
import { ref } from "vue";
import { analyticsApi } from "@/api/analytics.api";
import type { OverviewStats } from "@/types/analytics.types";

export const useAnalyticsStore = defineStore("analytics", () => {
  const overview = ref<OverviewStats | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchOverview() {
    loading.value = true;
    error.value = null;
    try {
      const { data } = await analyticsApi.getOverview();
      overview.value = data.data;
    } catch (e: any) {
      error.value = e?.response?.data?.message || "获取分析中心数据失败";
      overview.value = {
        total_tasks: 0,
        total_alerts: 0,
        pass_rate: 0,
        hallucination_rate: 0,
        risk_yellow_rate: 0,
      };
    } finally {
      loading.value = false;
    }
  }

  return { overview, loading, error, fetchOverview };
});
