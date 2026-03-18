import { defineStore } from "pinia";
import { ref } from "vue";
import { stabilityApi } from "@/api/stability.api";
import type { StabilityReport } from "@/types/stability.types";

export const useStabilityStore = defineStore("stability", () => {
  const current = ref<StabilityReport | null>(null);
  const loading = ref(false);

  async function fetchByTask(taskId: string) {
    loading.value = true;
    try {
      const { data } = await stabilityApi.getByTask(taskId);
      current.value = data.data;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  function $reset() {
    current.value = null;
  }

  return { current, loading, fetchByTask, $reset };
});
