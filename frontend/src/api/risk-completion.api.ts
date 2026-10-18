import { http } from "./http";
import type { ExportJob } from "@/types/governance.types";
export interface LabLink {
  id: string;
  status: string;
  revision: number;
  created_by: string;
  case_id: string;
  case_code: string;
  assessment_id: string;
  assessment_version: number;
  mode: "skip" | "verify";
  purpose: string;
  task_id: string | null;
  record_ids: string[];
  return_note?: string;
  added_new_evidence?: boolean;
  is_latest_assessment: boolean;
  issues: string[];
  boundary: string;
  events: Array<{ actor_name: string; action: string; at: string }>;
  execution_returns?: ExecutionReturn[];
}
export interface ExecutionSummary {
  item_verdict?: string | null;
  product_verdict?: string | null;
  risk_level?: string | null;
  complete_count?: number | null;
  expected_count?: number | null;
}
export interface ExecutionReturn {
  id: string;
  ref: { run_id: string; task_id: string; row_version: number; definition_hash: string;
    report_sources?: Array<{record_id: string; attachment_id: string}> };
  summary: ExecutionSummary | null;
  note: string;
  returned_by: string;
  returned_at: string;
  withdrawn_at: string | null;
  withdrawal_note?: string | null;
  issues: string[];
}
export interface ExecutionCandidate {
  id: string;
  row_version: number;
  reviewed_at: string | null;
  eligible: boolean;
  issues: string[];
  summary: ExecutionSummary | null;
  definition_hash: string | null;
  already_returned: boolean;
}
export interface ReportSummary {
  id: string;
  title: string;
  frozen_at: string;
  effective_status: string;
  source_issues: string[];
  validation_checked?: boolean;
}
export interface ReportPage {items: ReportSummary[]; next_cursor: string | null; has_more: boolean; size: number; notice: string}
export interface LabOption {id: string; label: string; status?: string; already_linked?: boolean}
export interface LabOptionPage {items: LabOption[]; selected: LabOption[]; unavailable_selected_ids: string[]; total: number; page: number; size: number}
export interface RiskReport extends ReportSummary {
  snapshot_hash: string;
  snapshot: {
    case_id: string;
    assessment_id: string;
    assessment_version: number;
    source_refs: Array<{ id: string; kind: string; hash: string }>;
  };
  sections: Array<{ title: string; paragraphs?: string[]; rows?: string[][]; columns?: string[] }>;
}
const quiet = { suppressErrorToast: true };
export const riskCompletionApi = {
  labs: (caseId: string) =>
    http.get<LabLink[]>(`/v1/risk-cases/${caseId}/laboratory-verifications`, quiet),
  labOptions: (caseId: string) =>
    http.get<{
      tasks: Array<{ id: string; label: string; status: string }>;
      records: Array<{ id: string; label: string; already_linked: boolean }>;
    }>(`/v1/risk-cases/${caseId}/laboratory-options`, quiet),
  decide: (
    caseId: string,
    data: {
      assessment_id: string;
      expected_basis_hash: string;
      expected_revision: number | null;
      mode: "skip" | "verify";
      purpose: string;
      task_id: string | null;
    },
  ) => http.post<LabLink>(`/v1/risk-cases/${caseId}/laboratory-verifications`, data, quiet),
  returnRecords: (
    id: string,
    data: { expected_revision: number; record_ids: string[]; note: string },
  ) => http.post<LabLink>(`/v1/risk-laboratory-verifications/${id}/evidence`, data, quiet),
  reports: (caseId?: string) =>
    http.get<ReportSummary[]>("/v1/risk-reports", { ...quiet, params: { case_id: caseId } }),
  reportPage: (params: {case_id?: string; cursor?: string; keyword?: string; size?: number}) =>
    http.get<ReportPage>('/v1/risk-report-pages', {...quiet, params}),
  labOptionPage: (caseId: string, kind: 'tasks' | 'records', params: {page: number; keyword: string; selected_ids: string[]}) =>
    http.get<LabOptionPage>(`/v1/risk-cases/${caseId}/laboratory-${kind}-options`, {...quiet,
      params:{...params, size:20}, paramsSerializer:{indexes:null}}),
  report: (id: string) => http.get<RiskReport>(`/v1/risk-reports/${id}`, quiet),
  executionCandidates: (id: string, page = 1) =>
    http.get<{items: ExecutionCandidate[]; total: number; page: number; size: number}>(
      `/v1/risk-laboratory-verifications/${id}/execution-results`, {...quiet, params:{page, size:20}}),
  returnExecution: (id: string, data: {expected_revision: number; run_id: string; expected_run_hash: string; note: string}) =>
    http.post<LabLink>(`/v1/risk-laboratory-verifications/${id}/execution-results`, data, quiet),
  withdrawExecution: (id: string, returnId: string, data: {expected_revision: number; note: string}) =>
    http.post<LabLink>(`/v1/risk-laboratory-verifications/${id}/execution-results/${returnId}/withdraw`, data, quiet),
  createReport: (caseId: string, assessmentId: string, basis: string) =>
    http.post<RiskReport>(
      `/v1/risk-cases/${caseId}/reports`,
      { assessment_id: assessmentId, expected_basis_hash: basis },
      quiet,
    ),
  exportReport: (id: string, format: "pdf" | "docx") =>
    http.post<ExportJob>(`/v1/risk-reports/${id}/exports`, { format }, quiet),
};
