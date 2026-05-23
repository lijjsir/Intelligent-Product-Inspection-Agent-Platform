import { http } from "./http";
import type { PagedResponse, PageParams } from "@/types/common.types";
import type { AuditLog, AuthLog } from "@/types/governance.types";

export interface AuthLogQuery extends Partial<PageParams> {
  user_id?: string;
  event_type?: string;
  ip_address?: string;
  start_date?: string;
  end_date?: string;
}

export interface AuditLogQuery extends Partial<PageParams> {
  actor_id?: string;
  resource_type?: string;
  action?: string;
  start_date?: string;
  end_date?: string;
}

export const logCenterApi = {
  listAuthLogs(params: AuthLogQuery) {
    return http.get<PagedResponse<AuthLog>>("/v1/auth-logs", { params });
  },
  listAuditLogs(params: AuditLogQuery) {
    return http.get<PagedResponse<AuditLog>>("/v1/audit-logs", { params });
  },
};
