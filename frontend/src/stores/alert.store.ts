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

  function _updateItem(id: string, updated: AlertEvent) {
    const idx = items.value.findIndex((a) => a.id === id);
    if (idx !== -1) {
      items.value[idx] = updated;
    }
  }

  async function ackAlert(id: string, actionNote?: string) {
    const { data } = await alertApi.handle(id, { action: "acknowledge", action_note: actionNote });
    _updateItem(id, data.data);
  }

  async function suppressAlert(id: string, actionNote: string) {
    const { data } = await alertApi.handle(id, { action: "suppress", action_note: actionNote });
    _updateItem(id, data.data);
  }

  async function resolveAlert(id: string, actionNote?: string) {
    const { data } = await alertApi.handle(id, { action: "resolve", action_note: actionNote });
    _updateItem(id, data.data);
  }

  return { items, total, loading, fetchAlerts, ackAlert, suppressAlert, resolveAlert };
});
