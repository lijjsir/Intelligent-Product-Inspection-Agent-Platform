import { http } from "./http";
import type { QualityReport, QualityTraceDeleteResult, QualityTraceListResponse } from "@/types/governance.types";

export const qualityApi = {
  getReport(params?: { start_date?: string; end_date?: string; source?: "all" | "inspection" | "chat"; include_remote?: boolean }) {
    return http.get<QualityReport>("/v1/quality/report", { params });
  },
  listTraces(params?: { source?: "all" | "inspection" | "chat"; limit?: number }) {
    return http.get<QualityTraceListResponse>("/v1/quality/traces", { params });
  },
  deleteTrace(traceId: string) {
    return http.delete<QualityTraceDeleteResult>(`/v1/quality/traces/${encodeURIComponent(traceId)}`);
  },
};
