import { http } from "./http";
import type { StabilityReport } from "@/types/stability.types";

export const stabilityApi = {
  getByTask(taskId: string) {
    return http.get<StabilityReport>(`/v1/stability/by-task/${taskId}`);
  },
};
