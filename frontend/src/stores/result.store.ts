import { defineStore } from "pinia";
import { ref } from "vue";
import { resultApi } from "@/api/result.api";
import type { InspectionResult, ResultListItem, ResultListQuery } from "@/types/result.types";

export const useResultStore = defineStore("result", () => {
  const items = ref<ResultListItem[]>([]);
  const current = ref<InspectionResult | null>(null);
  const total = ref(0);
  const loading = ref(false);

  async function fetchResults(query: ResultListQuery) {
    loading.value = true;
    try {
      const { data } = await resultApi.list(query);
      items.value = data.data.items;
      total.value = data.data.total;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

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
    items.value = [];
    current.value = null;
    total.value = 0;
  }

  return { items, current, total, loading, fetchResults, fetchByTask, $reset };
});
