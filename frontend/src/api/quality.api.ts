import { http } from "./http";
import type { QualityReport, QualityTraceItem } from "@/types/governance.types";

export const qualityApi = {
  getReport(params?: { start_date?: string; end_date?: string; source?: "all" | "inspection" | "chat" }) {
    return http.get<QualityReport>("/v1/quality/report", { params });
  },
  listTraces(params?: { source?: "all" | "inspection" | "chat"; limit?: number }) {
    return http.get<QualityTraceItem[]>("/v1/quality/traces", { params });
  },
};

