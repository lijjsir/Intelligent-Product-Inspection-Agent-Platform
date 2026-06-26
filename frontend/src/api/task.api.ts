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

export interface TaskStreamOptions {
  onOpen?: () => void;
  onError?: () => void;
  onHeartbeat?: (event: TaskStreamEvent) => void;
}

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

  create(payload: TaskCreate, config?: ApiRequestConfig) {
    return http.post<InspectionTask>("/v1/tasks", payload, config);
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

  async stream(
    taskId: string,
    onMessage: (event: TaskStreamEvent) => void,
    options: TaskStreamOptions = {},
  ): Promise<EventSource> {
    const { data } = await streamApi.create("task", taskId);
    const token = data.data.stream_token;
    const sep = apiBase.endsWith("/") ? "" : "/";
    const url = `${apiBase}${sep}v1/agent/tasks/${taskId}/stream?token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    const parse = (evt: MessageEvent<string>): TaskStreamEvent => {
      try {
        return JSON.parse(evt.data) as TaskStreamEvent;
      } catch {
        return { type: "raw", message: evt.data };
      }
    };
    source.onopen = () => options.onOpen?.();
    source.onerror = () => options.onError?.();
    source.onmessage = (evt) => {
      onMessage(parse(evt));
    };
    const consumeLifecycleEvent = (evt: MessageEvent<string>) => {
      options.onHeartbeat?.(parse(evt));
    };
    source.addEventListener("ready", consumeLifecycleEvent as EventListener);
    source.addEventListener("heartbeat", consumeLifecycleEvent as EventListener);
    return source;
  },
};
