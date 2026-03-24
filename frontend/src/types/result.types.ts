export type Verdict = 'pass' | 'fail' | 'uncertain' | 'manual_required';

export interface Defect {
  id?: string;
  type: string;
  confidence: number;
  bbox: [number, number, number, number];
  description?: string;
}

export interface InspectionResult {
  id: string;
  task_id: string;
  org_id: string;
  verdict: Verdict;
  overall_score: number;
  defects: Defect[] | null;
  citations: Record<string, any> | null;
  reasoning_chain: Record<string, any> | null;
  llm_model: string;
  prompt_version: string;
  tokens_used: number | null;
  latency_ms: number | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string | null;
}

export interface ResultListItem {
  id: string;
  task_id: string;
  org_id: string;
  product_id: string;
  verdict: Verdict;
  overall_score: number;
  llm_model: string;
  prompt_version: string;
  created_at: string | null;
}

export interface ResultListQuery {
  page: number;
  size: number;
  verdict?: Verdict;
  product_id?: string;
  model_key?: string;
}
