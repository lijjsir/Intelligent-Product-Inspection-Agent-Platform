import { defineStore } from "pinia";
import { ref } from "vue";
import { alertRuleApi } from "@/api/alert-rule.api";
import type { AlertRule, AlertRuleCreate, AlertRuleUpdate, AlertRuleListQuery } from "@/types/alert-rule.types";

export const useAlertRuleStore = defineStore("alertRule", () => {
  const items = ref<AlertRule[]>([]);
  const total = ref(0);
  const loading = ref(false);

  async function fetchRules(query: AlertRuleListQuery) {
    loading.value = true;
    try {
      const { data } = await alertRuleApi.list(query);
      items.value = data.data.items;
      total.value = data.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function createRule(payload: AlertRuleCreate) {
    const { data } = await alertRuleApi.create(payload);
    items.value.unshift(data.data);
    total.value++;
    return data.data;
  }

  async function updateRule(id: string, payload: AlertRuleUpdate) {
    const { data } = await alertRuleApi.update(id, payload);
    const idx = items.value.findIndex((r) => r.id === id);
    if (idx !== -1) items.value[idx] = data.data;
    return data.data;
  }

  async function deleteRule(id: string) {
    await alertRuleApi.delete(id);
    items.value = items.value.filter((r) => r.id !== id);
    total.value--;
  }

  return { items, total, loading, fetchRules, createRule, updateRule, deleteRule };
});
