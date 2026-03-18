import { defineStore } from "pinia";
import { ref } from "vue";
import { alertApi } from "@/api/alert.api";
import type { AlertEvent, AlertListQuery } from "@/types/alert.types";

export const useAlertStore = defineStore("alert", () => {
  const items = ref<AlertEvent[]>([]);
  const total = ref(0);
  const loading = ref(false);

  async function fetchAlerts(query: AlertListQuery) {
    loading.value = true;
    try {
      const { data } = await alertApi.list(query);
      items.value = data.data.items;
      total.value = data.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function resolveAlert(id: string) {
    loading.value = true;
    try {
      await alertApi.resolve(id);
      const idx = items.value.findIndex(a => a.id === id);
      if (idx !== -1) {
        items.value[idx].status = 'resolved';
      }
    } finally {
      loading.value = false;
    }
  }

  return { items, total, loading, fetchAlerts, resolveAlert };
});
