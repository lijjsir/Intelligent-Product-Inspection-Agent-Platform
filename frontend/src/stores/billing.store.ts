import { defineStore } from "pinia";
import { ref } from "vue";
import { billingApi } from "@/api/billing.api";
import type { ApiRequestConfig } from "@/api/http";
import type { BillingQuery, BillingSummary, CurrentUserTokenUsage } from "@/types/governance.types";

export const useBillingStore = defineStore("billing", () => {
  const current = ref<BillingSummary | null>(null);
  const myUsage = ref<CurrentUserTokenUsage | null>(null);
  const loading = ref(false);
  const myUsageLoading = ref(false);
  const filters = ref<BillingQuery>({ granularity: "day" });

  async function fetchSummary(query?: BillingQuery) {
    loading.value = true;
    try {
      filters.value = { ...filters.value, ...(query || {}) };
      const { data } = await billingApi.getSummary(filters.value);
      current.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchMyUsage(config?: ApiRequestConfig) {
    myUsageLoading.value = true;
    try {
      const { data } = await billingApi.getMyUsage(config);
      myUsage.value = data.data;
    } finally {
      myUsageLoading.value = false;
    }
  }

  return { current, myUsage, loading, myUsageLoading, filters, fetchSummary, fetchMyUsage };
});
