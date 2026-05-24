import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { inspectionSpecApi } from "@/api/inspection_spec.api";
import type { ApiRequestConfig } from "@/api/http";
import type { InspectionSpec, InspectionSpecPayload } from "@/types/governance.types";

export const useInspectionSpecStore = defineStore("inspection-spec", () => {
  const items = ref<InspectionSpec[]>([]);
  const current = ref<InspectionSpec | null>(null);
  const loading = ref(false);
  const count = computed(() => items.value.length);

  async function fetchAll(config?: ApiRequestConfig) {
    loading.value = true;
    try {
      const { data } = await inspectionSpecApi.list(config);
      items.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchOne(id: string) {
    const { data } = await inspectionSpecApi.get(id);
    current.value = data.data;
    return data.data;
  }

  async function createOne(payload: InspectionSpecPayload) {
    const { data } = await inspectionSpecApi.create(payload);
    items.value.unshift(data.data);
    return data.data;
  }

  async function updateOne(id: string, payload: Partial<InspectionSpecPayload>) {
    const { data } = await inspectionSpecApi.update(id, payload);
    const index = items.value.findIndex((item) => item.id === id);
    if (index !== -1) {
      items.value[index] = data.data;
    }
    if (current.value?.id === id) {
      current.value = data.data;
    }
    return data.data;
  }

  async function removeOne(id: string) {
    await inspectionSpecApi.remove(id);
    items.value = items.value.filter((item) => item.id !== id);
    if (current.value?.id === id) {
      current.value = null;
    }
  }

  function $reset() {
    items.value = [];
    current.value = null;
  }

  return { items, current, loading, count, fetchAll, fetchOne, createOne, updateOne, removeOne, $reset };
});
