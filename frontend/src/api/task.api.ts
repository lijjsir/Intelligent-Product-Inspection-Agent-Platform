import { http } from "./http";
import type { InspectionTask, TaskCreate, TaskListQuery } from "@/types/task.types";
import type { PagedResponse } from "@/types/common.types";

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
};
