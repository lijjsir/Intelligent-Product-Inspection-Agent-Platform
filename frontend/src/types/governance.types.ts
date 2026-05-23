export interface ModelConfig {
  id: string;
  org_id: string | null;
  provider: string;
  model_key: string;
  display_name: string;
  source_type: "external" | "local";
  source_uri: string;
  endpoint: string;
  model_type: string;
  fine_tune_command_template?: string | null;
  offline_eval_command_template?: string | null;
  deployment_command_template?: string | null;
  runtime_env_json?: Record<string, unknown> | null;
  default_gpu_request?: number | null;
  default_cpu_request?: number | null;
  default_memory_gb?: number | null;
  priority: number;
  rpm_limit: number | null;
  input_price_per_million: number | null;
  output_price_per_million: number | null;
  is_active: boolean;
  health_status: string;
  health_message: string | null;
  has_api_key: boolean;
}

export type ModelType = "chat" | "embedding" | "multimodal";

export interface ModelConfigPayload {
  org_id?: string | null;
  provider: string;
  model_key: string;
  display_name: string;
  source_type?: "external" | "local";
  source_uri: string;
  endpoint: string;
  api_key?: string | null;
  model_type?: ModelType;
  fine_tune_command_template?: string | null;
  offline_eval_command_template?: string | null;
  deployment_command_template?: string | null;
  runtime_env_json?: Record<string, unknown> | null;
  default_gpu_request?: number | null;
  default_cpu_request?: number | null;
  default_memory_gb?: number | null;
  priority?: number;
  rpm_limit?: number | null;
  input_price_per_million?: number | null;
  output_price_per_million?: number | null;
  is_active?: boolean;
}

export interface HealthCheckResult {
  health_status: string;
  health_message?: string;
}

export interface HealthCheckAllResult {
  checked: number;
  healthy: number;
  degraded: number;
  unhealthy: number;
}

export interface BillingBucket {
  bucket: string;
  total_tokens: number;
  total_cost: number;
  request_count: number;
}

export interface TokenLedger {
  id: string;
  user_id: string | null;
  model_key: string;
  product_line: string | null;
  total_tokens: number;
  cost_amount: number;
  trace_id: string | null;
  created_at: string;
}

export interface BillingSummary {
  granularity: string;
  total_tokens: number;
  total_cost: number;
  buckets: BillingBucket[];
  ledger_items: TokenLedger[];
  user_summaries: UserTokenUsageSummary[];
}

export interface UserTokenUsageSummary {
  user_id: string;
  org_id: string;
  username: string;
  role: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost: number;
  request_count: number;
  last_ledger_at: string | null;
  updated_at: string | null;
}

export interface CurrentUserTokenUsage {
  user_id: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost: number;
  request_count: number;
  last_ledger_at: string | null;
}

export interface BillingQuery {
  start_date?: string;
  end_date?: string;
  granularity?: "day" | "week" | "month";
  model_key?: string;
  product_line?: string;
}

export interface ResultFeedback {
  id: string;
  org_id: string;
  result_id: string;
  actor_id: string;
  feedback_type: "up" | "down";
  rating: number | null;
  category: string | null;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export type MessageFeedbackTargetType = "chat" | "meeting";

export interface MessageFeedback {
  id: string;
  org_id: string;
  target_type: MessageFeedbackTargetType;
  target_id: string;
  actor_id: string;
  feedback_type: "up" | "down";
  rating: number | null;
  category: string | null;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackSubmitPayload {
  feedback_type: "up" | "down";
  rating?: number | null;
  category?: string | null;
  comment?: string | null;
}

export interface FeedbackQuery {
  page?: number;
  size?: number;
  result_id?: string;
  feedback_type?: "up" | "down";
}

export interface MessageFeedbackQuery {
  target_type: MessageFeedbackTargetType;
  target_ids?: string;
}

export interface TrendPoint {
  bucket: string;
  value: number;
}

export interface ModelQualityMetric {
  model_key: string;
  result_count: number;
  pass_rate: number;
  hallucination_rate: number;
  thumbs_down_rate: number;
}

export interface QualityReport {
  total_results: number;
  hallucination_rate: number;
  thumbs_down_rate: number;
  avg_risk_score: number;
  feedback_distribution: Record<string, number>;
  hallucination_trend: TrendPoint[];
  thumbs_down_trend: TrendPoint[];
  model_metrics: ModelQualityMetric[];
  chat_score_count: number;
  chat_avg_trust_score: number;
  chat_hallucination_rate: number;
  chat_overconfidence_rate: number;
  chat_citation_rate: number;
  chat_trust_trend: TrendPoint[];
}

export interface QualityTraceItem {
  source_type: "inspection" | "chat" | string;
  trace_id: string;
  trace_url: string | null;
  result_id: string | null;
  task_id: string | null;
  assistant_message_id: string | null;
  session_id: string | null;
  observation_id: string | null;
  verdict: string | null;
  model_key: string | null;
  total_tokens: number;
  feedback_count: number;
  thumbs_down_count: number;
  last_score_value: number | null;
  last_score_at: string | null;
  trust_score: number | null;
  hallucination_risk: number | null;
  overconfidence: number | null;
  has_citation: boolean | null;
  score_status: string | null;
  review_model: string | null;
  langfuse_status: "synced" | "missing" | "local_only" | "unknown" | string | null;
  langfuse_synced: boolean | null;
  created_at: string | null;
}

export interface QualityTraceMeta {
  langfuse_enabled: boolean;
  langfuse_status: "ok" | "error" | "disabled" | "unknown" | string;
  langfuse_error: string | null;
  source: "all" | "inspection" | "chat" | string;
  canonical_source: "langfuse" | "local" | string;
  item_count: number;
}

export interface QualityTraceListResponse {
  items: QualityTraceItem[];
  meta: QualityTraceMeta;
}

export interface QualityTraceDeleteResult {
  trace_id: string;
  deleted: boolean;
  status: "deleted" | "not_found" | "langfuse_failed" | "langfuse_disabled" | string;
  message: string;
  langfuse_deleted: boolean;
  local_cleaned: boolean;
  local_results_removed?: number;
  local_scores_removed?: number;
}

export interface InspectionSpecItem {
  id: string;
  defect_type: string;
  severity: string;
  disposition: string;
  confidence_threshold: number;
  zone_name: string | null;
  max_count: number | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface InspectionSpec {
  id: string;
  org_id: string | null;
  spec_code: string;
  name: string;
  version: string;
  product_id: string | null;
  required_image_count: number;
  ai_gate_confidence_threshold: number;
  ai_gate_evidence_threshold: number;
  ai_gate_traceability_threshold: number;
  auto_pass_enabled: boolean;
  is_active: boolean;
  items: InspectionSpecItem[];
  created_at: string;
  updated_at: string;
}

export interface InspectionSpecItemPayload {
  defect_type: string;
  severity: string;
  disposition: string;
  confidence_threshold: number;
  zone_name?: string | null;
  max_count?: number | null;
  description?: string | null;
}

export interface InspectionSpecPayload {
  org_id?: string | null;
  spec_code: string;
  name: string;
  version?: string;
  product_id?: string | null;
  required_image_count?: number;
  ai_gate_confidence_threshold?: number;
  ai_gate_evidence_threshold?: number;
  ai_gate_traceability_threshold?: number;
  auto_pass_enabled?: boolean;
  is_active?: boolean;
  items: InspectionSpecItemPayload[];
}
