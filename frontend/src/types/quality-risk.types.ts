export type QualityRecordType =
  | "consumer_complaint"
  | "supervision_inspection"
  | "enforcement_case"
  | "enterprise_information"
  | "public_opinion"
  | "policy_document"
  | "standard_document"
  | "inspection_report"
  | "production_data"
  | "image"
  | "video"
  | "device_observation"
  | "expert_opinion";

export interface ProductCategoryV4 {
  classification_basis?: string | null;
  display_no?: string | null;
  id: string;
  org_id: string;
  code: string;
  name: string;
  parent_id?: string | null;
  description?: string | null;
  is_active: boolean;
}

export interface QualityProduct {
  display_no?: string | null;
  id: string;
  org_id: string;
  category_id: string;
  category_name?: string | null;
  name: string;
  model?: string | null;
  brand?: string | null;
  manufacturer_enterprise_id?: string | null;
  manufacturer_enterprise_name?: string | null;
  attributes: Record<string, unknown>;
  batches?: QualityProductionBatch[];
  identifiers: Array<{
    id?: string;
    identifier_type: "model_code" | "sku" | "barcode" | "source_product_id";
    identifier_value: string;
    source_id?: string | null;
  }>;
  is_active: boolean;
}

export interface QualityDataSource {
  display_no?: string | null;
  id: string;
  code: string;
  name: string;
  source_type: string;
  connector_type: "manual" | "file" | "api" | "webhook" | "database_sync";
  config: Record<string, unknown>;
  status: "active" | "inactive";
}

export interface QualityProductCandidate {
  id: string;
  display_no?: string | null;
  name: string;
  brand?: string | null;
  model?: string | null;
  manufacturer_enterprise_name?: string | null;
  missing_fields: string[];
  reason: string;
}

export interface QualityProductionBatch {
  id: string;
  product_id: string;
  display_no?: string | null;
  original_batch_no?: string | null;
  production_date?: string | null;
}

export interface QualityProductLinks {
  records: Array<{
    id: string;
    display_no?: string | null;
    record_type: QualityRecordType;
    origin_label?: string | null;
    received_at: string;
  }>;
  tasks: Array<{
    id: string;
    display_no?: string | null;
    status: string;
    has_result: boolean;
    created_at: string;
  }>;
}

export interface QualityAttachment {
  id: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  download_url: string;
}

export interface LocationRef {
  province_code?: string;
  city_code?: string;
  district_code?: string;
  formatted_address?: string;
  longitude?: number;
  latitude?: number;
  location_method?: "manual" | "browser" | "imported" | "source" | "unknown";
  accuracy_meters?: number;
}

export interface QualitySourceRecord {
  duplicate?: boolean;
  display_no?: string | null;
  id: string;
  source_id: string;
  ingestion_job_id?: string | null;
  external_record_id?: string | null;
  record_type: QualityRecordType;
  occurred_at: string | null;
  received_at: string;
  content: Record<string, any>;
  content_hash: string;
  enterprise_ref: Record<string, any>;
  product_ref: Record<string, any>;
  location: LocationRef;
  attachment_ids: string[];
  provenance: Record<string, any>;
  authorization_scope: string;
  data_nature: string;
  normalization_status: string;
  normalization_errors: any[];
  created_by: string;
}

export interface IntakeReferenceOptions {
  categories: Array<{ id: string; name: string }>;
  products: Array<{
    id: string;
    name: string;
    category_id: string;
    brand?: string | null;
    model?: string | null;
  }>;
  enterprises: Array<{ id: string; name: string }>;
}

export interface QualityRecordContext {
  record: QualitySourceRecord;
  objects: Record<
    "enterprise" | "product" | "category",
    { id: string | null; name: string | null; status: "linked" | "unlinked" | "unavailable" }
  >;
  source: { id: string; name: string | null; status: string };
  attachments: QualityAttachment[];
  unavailable_attachment_ids: string[];
  related_cases: Array<{ id: string; code: string; title: string; status: string }>;
}

export interface RiskCaseV4 {
  assessment_purpose?: "current_supervision" | "historical_review";
  display_no?: string | null;
  id: string;
  code: string;
  title: string;
  scope_type:
    | "category"
    | "enterprise"
    | "product"
    | "production_batch"
    | "individual_unit"
    | "mixed";
  scope: Record<string, any>;
  status: string;
  evidence_ids: string[];
  source_record_ids: string[];
  assigned_to?: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface RiskAssessmentV4 {
  analysis_origin?: { mode: string; assessment_id: string; version: number } | null;
  analysis_summary?: { summary?: string; limitations?: string[] };
  purpose_review?: { purpose?: "current_supervision" | "historical_review"; required_inputs?: string[]; limitations?: string[]; boundary?: string };
  demo_workflow?: DemoRiskWorkflow | null;
  demo_validation?: {
    is_current: boolean;
    blockers: { code: string; message: string }[];
    boundary: string;
    basis_hash: string;
  } | null;
  submitted_by?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at?: string | null;
  source_validation?: {
    blockers: { code: string; message: string; evidence_id?: string }[];
    uncertainties: string[];
    checked_at?: string;
    boundary?: string;
  };
  effective_status?: string;
  id: string;
  risk_case_id: string;
  version: number;
  risk_type?: string | null;
  risk_level: "low" | "medium" | "high" | "critical" | "unknown";
  scope: Record<string, any>;
  evidence_ids: string[];
  standard_matches: any[];
  conflicts: any[];
  missing_inputs: any[];
  possible_causes: string[];
  recommendations: string[];
  trust_status: string;
  probability?: number | null;
  policy_version?: string | null;
  status: string;
  review_comment?: string | null;
}

export interface RiskWorkflowContext {
  enabled: boolean; execution_mode: "demo" | "business"; can_author: boolean; eligible: boolean;
  assessment_id: string | null; basis_hash: string; blockers: Array<{ message: string }>; boundary: string;
}

export interface RiskWorkspace {
  workflow_context?: RiskWorkflowContext | null;
  demo_context?: DemoRiskContext | null;
  case: RiskCaseV4;
  records: QualitySourceRecord[];
  unavailable_source_ids: string[];
  latest_assessment: RiskAssessmentV4 | null;
  assessment_versions: Array<{
    id: string;
    version: number;
    status: string;
    risk_level: string;
    created_at?: string | null;
    reviewed_at?: string | null;
  }>;
}

export interface RiskAnalysisJob {
  id: string; case_id: string; created_by: string;
  status: 'queued'|'running'|'succeeded'|'completed_with_warnings'|'failed'|'stale'|'cancelled';
  assessment_id: string|null; error_code: string|null; message: string;
  created_at: string; started_at: string|null; finished_at: string|null;
}

export interface DemoRiskContent {
  summary: string;
  reasoning: string;
  limitations: string;
  risk_type: string | null;
  risk_level: "unknown" | "low" | "medium" | "high" | "critical";
  cited_record_ids: string[];
  missing_inputs: string[];
  recommendations: string[];
}

export interface DemoRiskWorkflow {
  schema: string;
  revision: number;
  basis_hash: string;
  author_name: string;
  boundary: string;
  submitted_at?: string;
  content: DemoRiskContent;
  events: Array<{
    action: string;
    actor_id: string;
    actor_name: string;
    at: string;
    decision?: string;
    comment?: string;
    revision?: number;
  }>;
}

export interface DemoRiskContext {
  enabled: boolean;
  execution_mode: "demo";
  basis_hash: string;
  blockers: { code: string; message: string }[];
  boundary: string;
  can_author: boolean;
}

export const RECORD_TYPE_LABELS: Record<QualityRecordType, string> = {
  consumer_complaint: "消费投诉",
  supervision_inspection: "监督抽查",
  enforcement_case: "执法案例",
  enterprise_information: "企业信息",
  public_opinion: "舆情信息",
  policy_document: "政策文件",
  standard_document: "标准文件",
  inspection_report: "检测报告",
  production_data: "生产数据",
  image: "图像",
  video: "视频",
  device_observation: "设备观测",
  expert_opinion: "专家意见",
};
