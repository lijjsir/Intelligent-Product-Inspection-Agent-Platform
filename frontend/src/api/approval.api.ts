import { http } from "./http";
import type { Approval, ApprovalListQuery } from "@/types/governance.types";
import type { PagedResponse } from "@/types/common.types";

export const approvalApi = {
  list(params: ApprovalListQuery) {
    return http.get<PagedResponse<Approval>>("/v1/approvals", { params });
  },
  get(id: string) {
    return http.get<Approval>(`/v1/approvals/${id}`);
  },
  approve(id: string, comment?: string) {
    return http.post<Approval>(`/v1/approvals/${id}/approve`, { comment });
  },
  reject(id: string, comment?: string) {
    return http.post<Approval>(`/v1/approvals/${id}/reject`, { comment });
  },
  cancel(id: string) {
    return http.post<Approval>(`/v1/approvals/${id}/cancel`);
  },
};
