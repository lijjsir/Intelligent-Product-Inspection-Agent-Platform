import { http } from "./http";
import type {
  InspectionTask,
  TaskCreate,
  TaskListQuery,
  TaskRunResponse,
  TaskStatusResponse,
  TaskStreamEvent,
} from "@/types/task.types";
import type { PagedResponse } from "@/types/common.types";

const apiBase = import.meta.env.VITE_API_BASE ?? "/api";

export const taskApi = {
  list(query: TaskListQuery) {
    return http.get<PagedResponse<InspectionTask>>("/v1/tasks", { params: query });
  },

  get(id: string) {
    return http.get<InspectionTask>(`/v1/tasks/${id}`);
  },

  create(payload: TaskCreate) {
    return http.post<InspectionTask>("/v1/tasks", payload);
  },

  run(taskId: string) {
    return http.post<TaskRunResponse>(`/v1/agent/tasks/${taskId}/run`);
  },

  getStatus(taskId: string) {
    return http.get<TaskStatusResponse>(`/v1/tasks/${taskId}/status`);
  },

  stream(taskId: string, onMessage: (event: TaskStreamEvent) => void): EventSource {
    const token = localStorage.getItem("piap_token") || "";
    const sep = apiBase.endsWith("/") ? "" : "/";
    const url = `${apiBase}${sep}v1/agent/tasks/${taskId}/stream?token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    source.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        onMessage(data);
      } catch {
        onMessage({ type: "raw", message: evt.data });
      }
    };
    return source;
  },
};
