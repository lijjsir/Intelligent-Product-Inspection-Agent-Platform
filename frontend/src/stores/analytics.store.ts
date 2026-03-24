import { defineStore } from "pinia";
import { ref } from "vue";
import { analyticsApi } from "@/api/analytics.api";
import type { OverviewStats } from "@/types/analytics.types";

export const useAnalyticsStore = defineStore("analytics", () => {
  const overview = ref<OverviewStats | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchOverview(params?: { start_date?: string; end_date?: string }) {
    loading.value = true;
    error.value = null;
    try {
      const { data } = await analyticsApi.getOverview(params);
      overview.value = data.data;
    } catch (e: any) {
      error.value = e?.response?.data?.message || "获取分析中心数据失败";
      overview.value = {
        total_tasks: 0,
        total_alerts: 0,
        total_results: 0,
        total_cost: 0,
        pass_rate: 0,
        hallucination_rate: 0,
        risk_yellow_rate: 0,
        avg_risk_score: 0,
        avg_latency_ms: 0,
        task_trend: [],
        pass_rate_trend: [],
        hallucination_trend: [],
        risk_distribution_trend: [],
        risk_distribution: [],
        alert_distribution: [],
        model_metrics: [],
        product_line_series: [],
      };
    } finally {
      loading.value = false;
    }
  }

  return { overview, loading, error, fetchOverview };
});
