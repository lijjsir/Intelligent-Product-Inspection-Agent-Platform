import { http } from "./http";
import type {
  FeedbackQuery,
  FeedbackSubmitPayload,
  FeedbackSummary,
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
  summary() {
    return http.get<FeedbackSummary>("/v1/feedbacks/summary");
  },
  list(query: FeedbackQuery) {
    return http.get<PagedResponse<ResultFeedback>>("/v1/feedbacks", { params: query });
  },
  detail(id: string) {
    return http.get<ResultFeedback>(`/v1/feedbacks/${id}`);
  },
  updateStatus(id: string, payload: { status: string; resolution?: string }) {
    return http.patch<ResultFeedback>(`/v1/feedbacks/${id}/status`, payload);
  },
  assign(id: string, payload: { assigned_to: string }) {
    return http.patch<ResultFeedback>(`/v1/feedbacks/${id}/assign`, payload);
  },
  submitMessage(targetType: MessageFeedbackTargetType, targetId: string, payload: FeedbackSubmitPayload) {
    return http.post<MessageFeedback>(`/v1/feedbacks/messages/${targetType}/${targetId}`, payload);
  },
  listMessages(query: MessageFeedbackQuery) {
    return http.get<MessageFeedback[]>("/v1/feedbacks/messages", { params: query });
  },
};
