import { defineStore } from "pinia";
import { ref } from "vue";
import { feedbackApi } from "@/api/feedback.api";
import type { FeedbackQuery, FeedbackSubmitPayload, ResultFeedback } from "@/types/governance.types";

export const useFeedbackStore = defineStore("feedback", () => {
  const items = ref<ResultFeedback[]>([]);
  const total = ref(0);
  const loading = ref(false);
  const submittedResultIds = ref<string[]>([]);

  async function fetchList(query: FeedbackQuery) {
    loading.value = true;
    try {
      const { data } = await feedbackApi.list(query);
      items.value = data.data.items;
      total.value = data.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function submit(resultId: string, payload: FeedbackSubmitPayload) {
    loading.value = true;
    try {
      const { data } = await feedbackApi.submit(resultId, payload);
      submittedResultIds.value = [...new Set([...submittedResultIds.value, resultId])];
      const index = items.value.findIndex((item) => item.result_id === resultId && item.actor_id === data.data.actor_id);
      if (index !== -1) {
        items.value[index] = data.data;
      } else {
        items.value.unshift(data.data);
      }
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  return { items, total, loading, submittedResultIds, fetchList, submit };
});

