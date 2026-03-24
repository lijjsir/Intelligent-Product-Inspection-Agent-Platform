import { defineStore } from "pinia";
import { ref } from "vue";
import { billingApi } from "@/api/billing.api";
import type { BillingQuery, BillingSummary } from "@/types/governance.types";

export const useBillingStore = defineStore("billing", () => {
  const current = ref<BillingSummary | null>(null);
  const loading = ref(false);
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

  return { current, loading, filters, fetchSummary };
});

