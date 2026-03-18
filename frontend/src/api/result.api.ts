import { http } from "./http";
import type { InspectionResult } from "@/types/result.types";
import type { ResponseEnvelope } from "@/types/common.types";

export const resultApi = {
  getByTask(taskId: string) {
    return http.get<InspectionResult>(`/v1/results/by-task/${taskId}`);
  },
};
