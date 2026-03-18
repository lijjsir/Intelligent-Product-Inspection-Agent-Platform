import { defineStore } from "pinia";
import { ref } from "vue";
import { resultApi } from "@/api/result.api";
import type { InspectionResult } from "@/types/result.types";

export const useResultStore = defineStore("result", () => {
  const current = ref<InspectionResult | null>(null);
  const loading = ref(false);

  async function fetchByTask(taskId: string) {
    loading.value = true;
    try {
      const { data } = await resultApi.getByTask(taskId);
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
