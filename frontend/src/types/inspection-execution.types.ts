export interface ExecutionRun {id:string;task_id:string;row_version:number;status:string;effective_status:string;created_by:string;reviewed_by?:string;
  created_at?:string;session_id?:string;source_validation?:{blockers:{code:string;message:string;evidence_id?:string}[];uncertainties:string[]};
  review_history?:{id:string;actor_id:string;action:string;reason:string;evidence_refs:string[];verification_snapshot:any;created_at:string}[];
  current_source_issues:string[];snapshot:{sample_ids:string[];observations:any[];rules:any[];source_refs:any[];policy:any;task_context?:{selected_samples?:{id:string;label:string}[]}};
  evaluation:{item_verdict:string;product_verdict:string;requirement_groups?:Record<string,{count:number;verdict:string}>;checks:any[];missing_inputs:string[];review_reasons:string[];boundary:string;risk_level:string;consumed_evidence_ids:string[]}}

export interface ExecutionTaskContext {
  case_preparation?:{initial_execution_keys:string[];report_attachment_id:string;standard_refs:{revision_id:string;candidate_id:string;measurement_key:string}[];
    planned_items:{measurement_key:string;value:number;unit:string;report_page:number;report_item:string;method:string;conditions_values:Record<string,unknown>}[]}|null;
  context_hash:string;task_scope:{task_id:string;product_id:string;product_name:string;product_category:string;production_date:string|null;production_batch_ref:string|null;unit_serial_ref:string|null;input_mode:string;issues:string[]};
  images:{image_hash:string;index:number;view:string}[];
  samples:{id:string;label:string;kind:string;code?:string;report_attachment_id?:string;issues:string[]}[];
  sessions:{id:string;label:string;code:string;sample_ids:string[];product_category?:string;production_date?:string}[];
  measurements:{id:string;session_id:string;sample_id:string;validation_status:string;data:{item:string;value:number;unit:string;method:string;conditions?:Record<string,unknown>;uncertainty?:number;quality_flag:string;measured_at?:string}}[];
  reports:{attachment_id:string;source_record_id:string;file_name?:string;page_count?:number;issues:string[];samples:{id:string;label:string}[]}[];
  policies:{id:string;snapshot:any;published_at?:string;definition_hash:string;issues:string[]}[];
  truncated:{sessions:boolean;samples:boolean;measurements:boolean};
}

export interface InspectionCaseWorkflow {
  case_id:string;title:string;steps:{key:string;label:string;status:'complete'|'pending';detail:string}[];
  limitations:string[];planned_items:{measurement_key:string;indicator:string;value:number;unit:string;report_page:number;original_pdf_page:number;minimum_observations:number}[];
  initial_execution_keys:string[];standard_document_id:string|null;standard_revision_id:string|null;standard_no:string|null;
  can_prepare_execution:boolean;execution_run_id:string|null;product_verdict:string;professional_work_complete:boolean;retrieval_reuse_verified:boolean;
}
