import { http } from "./http";
import type {
  SupervisionKind,
  SupervisionRecord,
  SupervisionRun,
  BusinessTodo,
  InspectionDecision,
  InspectionEvidenceState,
  InspectionGoal,
  InspectionTestItem,
} from "@/types/supervision.types";
import type { PagedResponse } from "@/types/common.types";

export const supervisionApi = {
  createInspectionGoal: (
    sessionId: string,
    payload: {
      session_version: number;
      request_key: string;
      plan_id?: string;
      risk_hypotheses: string[];
      required_items: InspectionTestItem[];
      candidate_items: InspectionTestItem[];
      success_criteria: Record<string, unknown>;
      stop_policy: {
        rule_version: string;
        evidence_sufficiency_threshold: number;
        max_rounds?: number;
        allow_early_stop?: boolean;
        require_expert_approval?: boolean;
      };
      max_cost?: number;
      max_duration_seconds?: number;
    },
  ) => http.post<InspectionGoal>(`/v1/inspection-sessions/${sessionId}/goals`, payload),
  inspectionGoal: (sessionId: string) =>
    http.get<InspectionGoal>(`/v1/inspection-sessions/${sessionId}/goal`, {
      suppressErrorToast: true,
    }),
  inspectionEvidenceState: (sessionId: string) =>
    http.get<InspectionEvidenceState>(`/v1/inspection-sessions/${sessionId}/evidence-state`, {
      suppressErrorToast: true,
    }),
  proposeNextTest: (
    sessionId: string,
    payload: { evidence_state_id: string; request_key: string; rule_version: string },
  ) =>
    http.post<InspectionDecision>(
      `/v1/inspection-sessions/${sessionId}/next-test-decisions`,
      payload,
    ),
  proposeStop: (
    sessionId: string,
    payload: { evidence_state_id: string; request_key: string; rule_version: string },
  ) =>
    http.post<InspectionDecision>(`/v1/inspection-sessions/${sessionId}/stop-decisions`, payload),
  reviewStopDecision: (
    sessionId: string,
    decisionId: string,
    payload: { decision: "approve" | "reject"; comment: string },
  ) =>
    http.post<InspectionDecision>(
      `/v1/inspection-sessions/${sessionId}/stop-decisions/${decisionId}/decision`,
      payload,
    ),
  datasetTargets: () =>
    http.get<{ value: string; label: string }[]>("/v1/quality-supervision/dataset-targets"),
  enrollDataset: (id: string, dataset_id: string) =>
    http.post(`/v1/inspection-sessions/${id}/dataset-enrollments`, { dataset_id }),
  enrollments: () => http.get<SupervisionRecord[]>("/v1/quality-supervision/dataset-enrollments"),
  settings: () =>
    http.get<{ enabled: boolean; permissions: string[] }>("/v1/quality-supervision/settings", {
      suppressErrorToast: true,
    }),
  assignees: () =>
    http.get<{ value: string; label: string }[]>("/v1/quality-supervision/assignees"),
  manualAssessment: (id: string, payload: Record<string, any>) =>
    http.post<SupervisionRecord>(`/v1/risk-cases/${id}/manual-assessment`, payload),
  reassessment: (id: string) =>
    http.post<SupervisionRecord>(`/v1/risk-cases/${id}/reassessment`, {}),
  enable: (enabled: boolean) =>
    http.patch("/v1/quality-supervision/settings", {}, { params: { enabled } }),
  list: (kind: SupervisionKind, params: Record<string, any> = {}) =>
    http.get<PagedResponse<SupervisionRecord>>(`/v1/${kind}`, { params, suppressErrorToast: true }),
  get: (kind: SupervisionKind, id: string) => http.get<SupervisionRecord>(`/v1/${kind}/${id}`),
  create: (kind: SupervisionKind, payload: Record<string, any>) =>
    http.post<SupervisionRecord>(`/v1/${kind}`, payload),
  update: (kind: SupervisionKind, id: string, payload: Record<string, any>) =>
    http.patch<SupervisionRecord>(`/v1/${kind}/${id}`, payload),
  revisions: (kind: SupervisionKind, id: string) => http.get<any[]>(`/v1/${kind}/${id}/revisions`),
  run: (kind: SupervisionKind, id: string, version: number, operation: string) =>
    http.post<SupervisionRun>(`/v1/${kind}/${id}/runs`, {
      version,
      operation,
      request_key: `${operation}:${id}:${version}`,
    }),
  runStatus: (id: string) => http.get<SupervisionRun>(`/v1/supervision-runs/${id}`),
  retry: (id: string) => http.post(`/v1/supervision-runs/${id}/retry`, {}),
  cancel: (id: string) => http.post(`/v1/supervision-runs/${id}/cancel`, {}),
  review: (kind: SupervisionKind, id: string, version: number, operation: string) =>
    http.post(`/v1/${kind}/${id}/reviews`, { version, operation }),
  todos: () => http.get<BusinessTodo[]>("/v1/business-reviews", { suppressErrorToast: true }),
  decide: (id: string, decision: string, comment: string) =>
    http.post(`/v1/business-reviews/${id}/decision`, { decision, comment }),
  feedback: (kind: SupervisionKind, id: string, payload: Record<string, any>) =>
    http.post(`/v1/${kind}/${id}/feedback`, payload),
  connection: (id: string) => http.post<{ token: string }>(`/v1/devices/${id}/connection`, {}),
  runtime: (id: string, payload: Record<string, any>) =>
    http.patch(`/v1/devices/${id}/runtime`, payload),
  measurements: (id: string) =>
    http.get<Record<string, any>[]>(`/v1/inspection-sessions/${id}/measurements`),
  preview: (id: string, file: File, mapping: Record<string, string>) => {
    const data = new FormData();
    data.append("file", file);
    data.append("mapping", JSON.stringify(mapping));
    return http.post<any>(`/v1/inspection-sessions/${id}/imports/preview`, data);
  },
  confirm: (id: string, preview_id: string, source_key: string) =>
    http.post(
      `/v1/inspection-sessions/${id}/imports/confirm`,
      {},
      { params: { preview_id, source_key } },
    ),
  template: () =>
    http.get<Blob>("/v1/quality-supervision/measurement-template", { responseType: "blob" }),
  analytics: () => http.get<any>("/v1/quality-supervision/analytics", { suppressErrorToast: true }),
};
