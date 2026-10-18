import { http } from "./http";
import type {
  MarketCoverage,
  MarketFocus,
  MarketObjectType,
  MarketReport,
  MarketRule,
  MarketSignalDetail,
} from "@/types/market-monitoring.types";
import type { RiskCaseV4 } from "@/types/quality-risk.types";
const base = "/v1/market-monitoring";
const quiet = { suppressErrorToast: true };
export const marketApi = {
  scan: (payload: { as_of?: string; object_type: MarketObjectType }) =>
    http.post<MarketReport>(`${base}/scan`, payload, quiet),
  signal: (id: string) => http.get<MarketSignalDetail>(`${base}/signals/${id}`, quiet),
  convert: (id: string, target_case_id?: string) =>
    http.post<{ case: RiskCaseV4; reused: boolean }>(
      `${base}/signals/${id}/risk-case`,
      { target_case_id: target_case_id || null },
      quiet,
    ),
  rule: (payload: {
    min_current: number;
    min_increase: number;
    growth_factor: number;
    expected_version: number;
    reason: string;
  }) => http.patch<MarketRule>(`${base}/rule`, payload, quiet),
  coverage: () => http.get<MarketCoverage[]>(`${base}/coverage`, quiet),
  setCoverage: (payload: {
    source_id: string;
    record_type: string;
    start_at: string;
    end_at: string;
    reason: string;
  }) => http.put(`${base}/coverage`, payload, quiet),
  focuses: () => http.get<MarketFocus[]>(`${base}/focus-objects`, quiet),
  addFocus: (payload: { object_type: MarketObjectType; object_id: string; reason: string }) =>
    http.post<{ id: string; reused: boolean }>(`${base}/focus-objects`, payload, quiet),
  removeFocus: (id: string, reason: string) =>
    http.post(`${base}/focus-objects/${id}/archive`, { reason }, quiet),
};
