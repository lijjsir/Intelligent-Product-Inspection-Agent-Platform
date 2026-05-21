import { http } from "./http";
import type { InspectionResult, ResultListItem, ResultListQuery } from "@/types/result.types";
import type { PagedResponse } from "@/types/common.types";

export interface ReviewSubmit {
  verdict: string;
  note?: string | null;
}

export const resultApi = {
  list(query: ResultListQuery) {
    return http.get<PagedResponse<ResultListItem>>("/v1/results", { params: query });
  },
  getByTask(taskId: string) {
    return http.get<InspectionResult>(`/v1/results/by-task/${taskId}`);
  },
  review(resultId: string, payload: ReviewSubmit) {
    return http.patch<InspectionResult>(`/v1/results/${resultId}/review`, payload);
  },
};
