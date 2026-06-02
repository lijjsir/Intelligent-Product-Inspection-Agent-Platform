import { defineStore } from "pinia";
import { ref } from "vue";
import { resultApi } from "@/api/result.api";
import type { InspectionResult, ResultListItem, ResultListQuery } from "@/types/result.types";
import type { PagedResponse } from "@/types/common.types";

const BACKEND_UNAVAILABLE_MESSAGE = "后端暂不可用，正在恢复连接；已保留当前列表数据。";

export const useResultStore = defineStore("result", () => {
  const items = ref<ResultListItem[]>([]);
  const current = ref<InspectionResult | null>(null);
  const total = ref(0);
  const loading = ref(false);
  const listError = ref("");

  async function fetchResults(query: ResultListQuery): Promise<PagedResponse<ResultListItem>> {
    loading.value = true;
    try {
      const { data } = await resultApi.list(query, { suppressErrorToast: true });
      items.value = data.data.items;
      total.value = data.data.total;
      listError.value = "";
      return data.data;
    } catch {
      listError.value = BACKEND_UNAVAILABLE_MESSAGE;
      return {
        items: items.value,
        total: total.value,
        page: Number(query.page || 1),
        size: Number(query.size || items.value.length || 20),
      };
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
    listError.value = "";
  }

  return { items, current, total, loading, listError, fetchResults, fetchByTask, $reset };
});
