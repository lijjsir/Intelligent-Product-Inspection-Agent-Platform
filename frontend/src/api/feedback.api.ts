import { http } from "./http";
import type { FeedbackQuery, FeedbackSubmitPayload, ResultFeedback } from "@/types/governance.types";
import type { PagedResponse } from "@/types/common.types";

export const feedbackApi = {
  submit(resultId: string, payload: FeedbackSubmitPayload) {
    return http.post<ResultFeedback>(`/v1/feedbacks/results/${resultId}`, payload);
  },
  list(query: FeedbackQuery) {
    return http.get<PagedResponse<ResultFeedback>>("/v1/feedbacks", { params: query });
  },
};

