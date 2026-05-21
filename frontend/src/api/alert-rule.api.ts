import { http } from "./http";
import type { AlertRule, AlertRuleCreate, AlertRuleUpdate, AlertRuleListQuery } from "@/types/alert-rule.types";
import type { PagedResponse } from "@/types/common.types";

export const alertRuleApi = {
  list(query: AlertRuleListQuery) {
    return http.get<PagedResponse<AlertRule>>("/v1/alerts/rules", { params: query });
  },
  get(id: string) {
    return http.get<AlertRule>(`/v1/alerts/rules/${id}`);
  },
  create(payload: AlertRuleCreate) {
    return http.post<AlertRule>("/v1/alerts/rules", payload);
  },
  update(id: string, payload: AlertRuleUpdate) {
    return http.put<AlertRule>(`/v1/alerts/rules/${id}`, payload);
  },
  delete(id: string) {
    return http.delete<boolean>(`/v1/alerts/rules/${id}`);
  },
};
