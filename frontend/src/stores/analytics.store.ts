import { defineStore } from "pinia";
import { ref } from "vue";
import { analyticsApi } from "@/api/analytics.api";
import type { OverviewStats } from "@/types/analytics.types";

export const useAnalyticsStore = defineStore("analytics", () => {
  const overview = ref<OverviewStats | null>(null);
  const loading = ref(false);

  async function fetchOverview() {
    loading.value = true;
    try {
      const { data } = await analyticsApi.getOverview();
      overview.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  return { overview, loading, fetchOverview };
});
