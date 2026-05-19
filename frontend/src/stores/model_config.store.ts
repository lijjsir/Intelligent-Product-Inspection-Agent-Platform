import { defineStore } from "pinia";
import { ref } from "vue";
import { modelConfigApi } from "@/api/model_config.api";
import type { ModelConfig, ModelConfigPayload } from "@/types/governance.types";

export const useModelConfigStore = defineStore("model-config", () => {
  const items = ref<ModelConfig[]>([]);
  const loading = ref(false);

  async function fetchAll() {
    loading.value = true;
    try {
      const { data } = await modelConfigApi.list();
      items.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  async function createOne(payload: ModelConfigPayload) {
    const { data } = await modelConfigApi.create(payload);
    items.value.unshift(data.data);
    return data.data;
  }

  async function updateOne(id: string, payload: Partial<ModelConfigPayload>) {
    const { data } = await modelConfigApi.update(id, payload);
    const index = items.value.findIndex((item) => item.id === id);
    if (index !== -1) items.value[index] = data.data;
    return data.data;
  }

  async function removeOne(id: string) {
    await modelConfigApi.remove(id);
    items.value = items.value.filter((item) => item.id !== id);
  }

  async function checkHealth(id: string) {
    const { data } = await modelConfigApi.checkHealth(id);
    const index = items.value.findIndex((item) => item.id === id);
    if (index !== -1) {
      items.value[index] = { ...items.value[index], health_status: data.data.health_status, health_message: data.data.health_message ?? null };
    }
    return data.data;
  }

  async function checkHealthAll() {
    const { data } = await modelConfigApi.checkHealthAll();
    await fetchAll();
    return data.data;
  }

  return { items, loading, fetchAll, createOne, updateOne, removeOne, checkHealth, checkHealthAll };
});

