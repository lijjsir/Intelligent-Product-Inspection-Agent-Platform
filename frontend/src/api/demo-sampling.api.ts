import { http } from "./http";

export interface DemoSamplingContent {
  rationale: string;
  focus: string;
  limitations: string;
  sample_quantity: number | null;
  batch: string | null;
  location: string | null;
  proposed_time: string | null;
}
export interface DemoSamplingSnapshot {
  case_id: string;
  case_code: string;
  case_title: string;
  scope: Record<string, unknown>;
  objects: Array<{ kind: string; label: string; id: string; name: string }>;
  assessment_id: string;
  assessment_version: number;
  source_record_ids: string[];
  evidence_ids: string[];
  conclusion: { summary: string; limitations: string; missing_inputs: string[] };
  review: { reviewed_by: string; reviewed_at: string | null; comment: string };
  schema?:string;
  collaboration_id: string|null;
  collaboration_purpose: string;
  decision_note: string;
  opinions: Array<{ id: string; author: string; origin: string; content: string }>;
  source_link: string;
  execution_mode: "demo" | "business";
  llm_called: boolean;
}
export interface DemoSamplingCandidate {
  snapshot: DemoSamplingSnapshot;
  context_hash: string;
}
export interface DemoSamplingSuggestion extends DemoSamplingCandidate {
  id: string;
  title: string;
  status: "demo_draft" | "demo_confirmed" | "draft" | "confirmed";
  effective_status: string;
  revision: number;
  is_current: boolean;
  stale_reason: string;
  can_edit: boolean;
  content: DemoSamplingContent;
  boundary: string;
  confirmed_at: string | null;
  events: Array<{ action: string; actor_name: string; at: string }>;
}
const quiet = { suppressErrorToast: true };
export interface SamplingPage<T> {items:T[];next_cursor:string|null;has_more:boolean;size:number;blockers:string[];boundary:string}
export const demoSamplingApi = {
  page: <T extends DemoSamplingCandidate | DemoSamplingSuggestion>(kind:'candidates'|'suggestions',params:{case_id?:string;cursor?:string;keyword?:string}) =>
    http.get<SamplingPage<T>>(`/v1/risk-sampling/pages/${kind}`,{...quiet,params:{...params,size:20}}),
  candidates: (caseId?: string) =>
    http.get<{ items: DemoSamplingCandidate[]; blockers: string[]; boundary: string }>(
      "/v1/risk-sampling/candidates",
      { ...quiet, params: { case_id: caseId } },
    ),
  list: (caseId?: string) =>
    http.get<DemoSamplingSuggestion[]>("/v1/risk-sampling/suggestions", {
      ...quiet,
      params: { case_id: caseId },
    }),
  get: (id: string) =>
    http.get<DemoSamplingSuggestion>(`/v1/risk-sampling/suggestions/${id}`, quiet),
  create: (candidate: DemoSamplingCandidate) =>
    http.post<DemoSamplingSuggestion>(
      `/v1/risk-cases/${candidate.snapshot.case_id}/risk-sampling-suggestions`,
      {
        assessment_id: candidate.snapshot.assessment_id,
        expected_context_hash: candidate.context_hash,
      },
      quiet,
    ),
  save: (id: string, revision: number, content: DemoSamplingContent) =>
    http.patch<DemoSamplingSuggestion>(
      `/v1/risk-sampling/suggestions/${id}`,
      { expected_revision: revision, content },
      quiet,
    ),
  confirm: (id: string, revision: number) =>
    http.post<DemoSamplingSuggestion>(
      `/v1/risk-sampling/suggestions/${id}/confirm`,
      { expected_revision: revision },
      quiet,
    ),
};
