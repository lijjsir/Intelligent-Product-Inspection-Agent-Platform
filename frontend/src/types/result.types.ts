export type Verdict = 'pass' | 'fail' | 'uncertain' | 'manual_required';

export interface TaskResultBundle {
  bundle_version:string;task:{id:string;product_id:string;product_name:string;spec_code:string};
  selection:{execution_run_id:string|null;legacy_only:boolean};execution_versions:{id:string;row_version:number;status:string;created_at:string;item_verdict:string}[];
  execution:import('./inspection-execution.types').ExecutionRun|null;auxiliary:any;risks:any[];
  scope:{stage:string;label:string;product_verdict:string;boundary:string};source_refs:any[];result_token:string;can_export:boolean;
}

export interface Defect {
  id?: string;
  type: string;
  confidence: number;
  bbox: [number, number, number, number];
  description?: string | null;
  image_index?: number | null;
  image_hash?: string | null;
}

export interface InspectionResult {
  score_status?: string;
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
  score_status?: string;
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
  task_id?: string;
}
