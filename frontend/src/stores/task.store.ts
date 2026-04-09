import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { taskApi } from "@/api/task.api";
import type { InspectionTask, TaskCreate, TaskListQuery, TaskStreamEvent } from "@/types/task.types";

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

  async function runTask(id: string) {
    const { data } = await taskApi.run(id);
    return data.data;
  }

  async function fetchTaskStatus(id: string) {
    const { data } = await taskApi.getStatus(id);
    return data.data;
  }

  function subscribeTaskStream(id: string, onMessage: (event: TaskStreamEvent) => void): () => void {
    const source = taskApi.stream(id, onMessage);
    return () => source.close();
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
    runTask,
    fetchTaskStatus,
    subscribeTaskStream,
    $reset,
  };
});
