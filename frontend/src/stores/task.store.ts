import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { taskApi } from "@/api/task.api";
import type {
  InspectionTask,
  TaskCreate,
  TaskListQuery,
  TaskResultIngestRequest,
  TaskStreamEvent,
} from "@/types/task.types";

export const useTaskStore = defineStore("task", () => {
  const items = ref<InspectionTask[]>([]);
  const current = ref<InspectionTask | null>(null);
  const total = ref(0);
  const loading = ref(false);

  const count = computed(() => items.value.length);

  async function fetchTasks(query: TaskListQuery) {
    loading.value = true;
    try {
      const { data } = await taskApi.list(query);
      items.value = data.data.items;
      total.value = data.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function fetchTask(id: string) {
    const { data } = await taskApi.get(id);
    current.value = data.data;
    return data.data;
  }

  async function createTask(payload: TaskCreate) {
    const { data } = await taskApi.create(payload);
    items.value.unshift(data.data);
    total.value++;
    return data.data;
  }

  async function deleteTask(id: string) {
    await taskApi.delete(id);
    items.value = items.value.filter((item) => item.id !== id);
    if (current.value?.id === id) {
      current.value = null;
    }
    total.value = Math.max(0, total.value - 1);
  }

  async function runTask(id: string) {
    const { data } = await taskApi.run(id);
    if (current.value?.id === id) {
      current.value = { ...current.value, status: data.data.status || "queued" };
    }
    await fetchTask(id);
    return data.data;
  }

  async function ingestTaskResult(id: string, payload: TaskResultIngestRequest) {
    const { data } = await taskApi.ingest(id, payload);
    return data.data;
  }

  async function fetchTaskEvents(id: string) {
    const { data } = await taskApi.events(id);
    return data.data.map((item: TaskStreamEvent & { event_type?: string; payload_json?: TaskStreamEvent; created_at?: string }) => ({
      ...(item.payload_json || item),
      id: item.id || item.payload_json?.id,
      type: String(item.type || item.event_type || item.payload_json?.type || "event"),
      status: item.status || item.payload_json?.status,
      stage: item.stage || item.payload_json?.stage,
      message: item.message || item.payload_json?.message,
      ts: item.ts || item.payload_json?.ts || item.created_at,
    }));
  }

  function subscribeTaskStream(id: string, onMessage: (event: TaskStreamEvent) => void): () => void {
    let source: EventSource | null = null;
    let closed = false;
    taskApi.stream(id, onMessage)
      .then((instance) => {
        if (closed) {
          instance.close();
          return;
        }
        source = instance;
      })
      .catch(() => undefined);
    return () => {
      closed = true;
      source?.close();
    };
  }

  function $reset() {
    items.value = [];
    current.value = null;
    total.value = 0;
  }

  return {
    items,
    current,
    total,
    loading,
    count,
    fetchTasks,
    fetchTask,
    createTask,
    deleteTask,
    runTask,
    ingestTaskResult,
    fetchTaskEvents,
    subscribeTaskStream,
    $reset,
  };
});
