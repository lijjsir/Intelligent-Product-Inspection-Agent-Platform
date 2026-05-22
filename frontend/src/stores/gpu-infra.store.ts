import { defineStore } from "pinia";
import { ref, computed } from "vue";

import { gpuInfraApi } from "@/api/gpu-infra.api";
import type { GpuComputeNode, GpuNodeCreatePayload, GpuNodeUpdatePayload } from "@/types/gpu-infra.types";

export const useGpuInfraStore = defineStore("gpu-infra", () => {
  const items = ref<GpuComputeNode[]>([]);
  const current = ref<GpuComputeNode | null>(null);
  const loading = ref(false);
  const onlineCount = computed(() => items.value.filter((item) => item.status === "online").length);
  const totalGpuCount = computed(() => items.value.reduce((sum, item) => sum + (item.total_gpu_count || 0), 0));
  const availableGpuCount = computed(() => items.value.reduce((sum, item) => sum + (item.available_gpu_count || 0), 0));
  const allocatedGpuCount = computed(() => totalGpuCount.value - availableGpuCount.value);

  async function fetchAll() {
    loading.value = true;
    try {
      const { data } = await gpuInfraApi.list();
      items.value = data.data;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchOne(id: string) {
    const { data } = await gpuInfraApi.get(id);
    current.value = data.data;
    return data.data;
  }

  async function createOne(payload: GpuNodeCreatePayload) {
    const { data } = await gpuInfraApi.create(payload);
    items.value.unshift(data.data);
    return data.data;
  }

  async function updateOne(id: string, payload: GpuNodeUpdatePayload) {
    const { data } = await gpuInfraApi.update(id, payload);
    const idx = items.value.findIndex((item) => item.id === id);
    if (idx !== -1) items.value[idx] = data.data;
    if (current.value?.id === id) current.value = data.data;
    return data.data;
  }

  async function removeOne(id: string) {
    await gpuInfraApi.remove(id);
    items.value = items.value.filter((item) => item.id !== id);
    if (current.value?.id === id) current.value = null;
  }

  async function testConnection(id: string) {
    const { data } = await gpuInfraApi.testConnection(id);
    return data.data;
  }

  async function refreshMetrics(id: string) {
    const { data } = await gpuInfraApi.refreshMetrics(id);
    const idx = items.value.findIndex((item) => item.id === id);
    if (idx !== -1) items.value[idx] = data.data.node;
    if (current.value?.id === id) current.value = data.data.node;
    return data.data;
  }

  async function toggleEnabled(id: string, enabled: boolean) {
    const { data } = enabled ? await gpuInfraApi.enable(id) : await gpuInfraApi.disable(id);
    const idx = items.value.findIndex((item) => item.id === id);
    if (idx !== -1) items.value[idx] = data.data;
    if (current.value?.id === id) current.value = data.data;
    return data.data;
  }

  return {
    items,
    current,
    loading,
    onlineCount,
    totalGpuCount,
    availableGpuCount,
    allocatedGpuCount,
    fetchAll,
    fetchOne,
    createOne,
    updateOne,
    removeOne,
    testConnection,
    refreshMetrics,
    toggleEnabled,
  };
});
