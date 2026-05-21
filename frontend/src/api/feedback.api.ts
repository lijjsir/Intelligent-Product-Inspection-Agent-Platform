import { http } from "./http";
import type {
  FeedbackQuery,
  FeedbackSubmitPayload,
  MessageFeedback,
  MessageFeedbackQuery,
  MessageFeedbackTargetType,
  ResultFeedback,
} from "@/types/governance.types";
import type { PagedResponse } from "@/types/common.types";

export const feedbackApi = {
  submit(resultId: string, payload: FeedbackSubmitPayload) {
    return http.post<ResultFeedback>(`/v1/feedbacks/results/${resultId}`, payload);
  },
  list(query: FeedbackQuery) {
    return http.get<PagedResponse<ResultFeedback>>("/v1/feedbacks", { params: query });
  },
  submitMessage(targetType: MessageFeedbackTargetType, targetId: string, payload: FeedbackSubmitPayload) {
    return http.post<MessageFeedback>(`/v1/feedbacks/messages/${targetType}/${targetId}`, payload);
  },
  listMessages(query: MessageFeedbackQuery) {
    return http.get<MessageFeedback[]>("/v1/feedbacks/messages", { params: query });
  },
};
