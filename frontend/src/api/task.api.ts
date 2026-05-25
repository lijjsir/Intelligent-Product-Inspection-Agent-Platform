import { http, type ApiRequestConfig } from "./http";
import { streamApi } from "./stream.api";
import type {
  InspectionTask,
  TaskCreate,
  TaskListQuery,
  TaskResultIngestRequest,
  TaskResultIngestResponse,
  TaskRunResponse,
  TaskStreamEvent,
} from "@/types/task.types";
import type { PagedResponse } from "@/types/common.types";

const apiBase = String(import.meta.env.VITE_API_BASE ?? "/api").trim();

export const taskApi = {
  list(query: TaskListQuery, config?: ApiRequestConfig) {
    return http.get<PagedResponse<InspectionTask>>("/v1/tasks", { ...config, params: query });
  },

  get(id: string) {
    return http.get<InspectionTask>(`/v1/tasks/${id}`);
  },

  events(id: string) {
    return http.get<TaskStreamEvent[]>(`/v1/tasks/${id}/events`);
  },

  create(payload: TaskCreate) {
    return http.post<InspectionTask>("/v1/tasks", payload);
  },

  delete(taskId: string) {
    return http.delete<{ deleted: boolean; task_id: string }>(`/v1/tasks/${taskId}`);
  },

  run(taskId: string) {
    return http.post<TaskRunResponse>(`/v1/agent/tasks/${taskId}/run`);
  },

  ingest(taskId: string, payload: TaskResultIngestRequest) {
    return http.post<TaskResultIngestResponse>(`/v1/tasks/${taskId}/ingest`, payload);
  },

  async stream(taskId: string, onMessage: (event: TaskStreamEvent) => void): Promise<EventSource> {
    const { data } = await streamApi.create("task", taskId);
    const token = data.data.stream_token;
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
