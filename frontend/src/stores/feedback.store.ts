import { defineStore } from "pinia";
import { ref } from "vue";
import { feedbackApi } from "@/api/feedback.api";
import type {
  FeedbackQuery,
  FeedbackSeverity,
  FeedbackStatus,
  FeedbackSubmitPayload,
  FeedbackSummary,
  ResultFeedback,
} from "@/types/governance.types";

export const useFeedbackStore = defineStore("feedback", () => {
  const items = ref<ResultFeedback[]>([]);
  const total = ref(0);
  const loading = ref(false);
  const summary = ref<FeedbackSummary | null>(null);
  const submittedResultIds = ref<string[]>([]);
  const currentDetail = ref<ResultFeedback | null>(null);

  async function fetchSummary() {
    const { data } = await feedbackApi.summary();
    summary.value = data.data;
  }

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

  async function fetchDetail(id: string) {
    const { data } = await feedbackApi.detail(id);
    currentDetail.value = data.data;
    return data.data;
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

  async function updateStatus(id: string, status: FeedbackStatus, resolution?: string) {
    const { data } = await feedbackApi.updateStatus(id, { status, resolution });
    const idx = items.value.findIndex((i) => i.id === id);
    if (idx !== -1) items.value[idx] = data.data;
    if (currentDetail.value?.id === id) currentDetail.value = data.data;
    return data.data;
  }

  async function assign(id: string, assignedTo: string) {
    const { data } = await feedbackApi.assign(id, { assigned_to: assignedTo });
    const idx = items.value.findIndex((i) => i.id === id);
    if (idx !== -1) items.value[idx] = data.data;
    if (currentDetail.value?.id === id) currentDetail.value = data.data;
    return data.data;
  }

  return {
    items, total, loading, summary, submittedResultIds, currentDetail,
    fetchSummary, fetchList, fetchDetail, submit, updateStatus, assign,
  };
});
