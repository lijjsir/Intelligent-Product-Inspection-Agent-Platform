export interface StandardCandidate {
  id: string; clause_no: string; page_number: number; source_text: string;
  candidate_type?: "inspection_requirement" | "method_condition" | "body_clause" | string;
  ocr_text?: string; normalized_text?: string; extraction_confidence?: number; normalization_notes?: string;
  source_extraction_method?: string; text_warnings?: string[];
  indicator: string; method: string; conditions: string; unit: string; requirement: string;
  operator: "le" | "ge" | "range" | "eq" | "text" | "unresolved";
  measurement_key: string; applicability: string; status: "pending" | "confirmed" | "rejected";
  execution_mode?:'manual'|'numeric';numeric_lower?:number|null;numeric_upper?:number|null;numeric_target?:number|null;
  decision_mode?:'direct'|'interval';numeric_aggregation?:'all'|'mean';minimum_observations?:number;expected_conditions?:Record<string,unknown>;
  missing_fields: string[]; warning: string; reviewed_by: string | null;
  prepared_by?: string | null; prepared_at?: string; reviewed_at?: string;
  review_reason?: string; review_evidence_refs?: string[];
}
export interface StandardRevision {
  id: string; document_id: string; revision_no: number; row_version: number;
  snapshot: Record<string, any>; file_hash: string | null;
  processing_status: string; review_status: string; publication_status: string; extraction_status: string;
  created_by: string | null; reviewed_by: string | null; created_at: string;
  published_by: string | null; published_at: string | null;
  review_assignment?: {reviewer_id: string|null; domain?:string; due_at?:string|null; mode:string; reason:string}|null;
  page_count: number; candidate_count: number; confirmed_count: number; issues: string[];
  pages?: { page_number: number; text: string; raw_text?: string; text_warnings?: string[] }[]; candidates?: StandardCandidate[];
  metadata_candidates?: Record<string,{value:string;page_number:number;source_text:string}>;
  reviews?: {id:string; action:string; actor_id:string; reason:string; evidence_refs:string[]; created_at:string}[];
  jobs?: {id:string; action:string; status:string; attempts:number; error_message:string|null; next_attempt_at:string|null}[];
}
export interface RevisionAction {
  expected_version: number; request_key: string; reason: string; evidence_refs: string[];
}

export interface StandardReviewRow {
  document_id:string;revision_id:string;revision_no:number;row_version:number;library_id:string;library_name:string;
  standard_no:string;standard_name:string;domain:string;product_category:string|null;
  created_by:string|null;created_at:string;processing_status:string;review_status:string;publication_status:string;
  pending_count:number;confirmed_count:number;candidate_count:number;excluded_count:number;
  needs_work:boolean;is_author:boolean;assigned_to_me:boolean;can_claim:boolean;can_review:boolean;
  review_assignment:{reviewer_id?:string|null;reviewer_name?:string;due_at?:string|null;domain?:string;reason?:string};
}
export interface StandardReviewQueue {
  items:StandardReviewRow[];total:number;page:number;size:number;domains:string[];
  totals:{pending:number;mine:number;unassigned:number;awaiting_publish:number};
}
