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
  thumbs_up_rate: number;
}

export interface QualityReport {
  total_results: number;
  hallucination_rate: number;
  thumbs_down_rate: number;
  thumbs_up_rate: number;
  thumbs_down_count: number;
  thumbs_up_count: number;
  feedback_total_count: number;
  thumbs_down_share: number;
  thumbs_up_share: number;
  avg_risk_score: number;
  feedback_distribution: Record<string, number>;
  hallucination_trend: TrendPoint[];
  thumbs_down_trend: TrendPoint[];
  thumbs_up_trend: TrendPoint[];
  model_metrics: ModelQualityMetric[];
  chat_message_count: number;
  chat_score_count: number;
  chat_unscored_count: number;
  chat_scored_rate: number;
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
  thumbs_up_count: number;
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

export interface RoleItem {
  key: string;
  label: string;
}

export interface RolesPermissionMatrix {
  resources: string[];
  matrix: Record<string, string[]>;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: string;
  settings?: Record<string, unknown> | null;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
  user_count: number;
}

export interface OrganizationCreatePayload {
  name: string;
  slug: string;
  plan: string;
  settings?: Record<string, unknown> | null;
}

export interface OrganizationUpdatePayload {
  name?: string;
  slug?: string;
  plan?: string;
  settings?: Record<string, unknown> | null;
  is_active?: boolean;
}

export interface OrganizationUserItem {
  id: string;
  username: string;
  role: string;
  is_active: boolean;
}

export interface OrganizationUsersResponse {
  organization: {
    id: string;
    name: string;
  };
  users: OrganizationUserItem[];
  total: number;
}

export interface OrganizationUserAssignmentPayload {
  user_ids: string[];
  action: "assign" | "remove";
}

export interface AuthLog {
  id: string;
  org_id: string;
  user_id?: string | null;
  username?: string | null;
  event_type: string;
  ip_address?: string | null;
  user_agent?: string | null;
  success: boolean;
  detail?: string | null;
  occurred_at?: string;
}

export interface AuditLog {
  id: string;
  org_id: string;
  actor_id: string;
  actor_role: string;
  resource_type: string;
  resource_id?: string | null;
  action: string;
  payload_hash?: string | null;
  request_id?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  result_code?: number | null;
  occurred_at?: string;
}

export interface InfrastructureComponent {
  name: string;
  kind: string;
  status: "healthy" | "degraded" | "unhealthy" | "unknown" | string;
  latency_ms?: number | null;
  detail?: string | null;
  last_check_at?: string | null;
}

export interface InfrastructureStatus {
  components: InfrastructureComponent[];
  overall_status: "healthy" | "degraded" | "unhealthy" | "unknown" | string;
  checked_at: string;
}

export interface MemorySearchQueryPayload {
  org_id: string;
  workspace: "governance" | "ops" | "app";
  query: string;
  user_id?: string | null;
  top_k?: number;
  scope_filter?: {
    memory_type?: string[];
    product_line?: string | null;
    rag_space_id?: string | null;
    task_id?: string | null;
  };
}

export interface MemorySearchItem {
  memory_id: string;
  memory_type: string;
  summary: string;
  score: number;
  confidence?: number | null;
  trust_score?: number | null;
  usage_policy?: string;
  warnings?: string[];
}

export interface MemorySearchResult {
  memory_context: {
    items: MemorySearchItem[];
    warnings: string[];
    degraded: boolean;
  };
  items: MemorySearchItem[];
  degraded: boolean;
  warnings: string[];
}

export interface MemoryEventItem {
  event_id: string;
  event_type: string;
  memory_id?: string | null;
  trace_id?: string | null;
  source_kind?: string | null;
  created_at?: string | null;
}

export interface MemoryPropagationNode {
  memory_id: string;
  classification: string;
  depth: number;
  edge_type?: string | null;
  affected_by: string[];
}

export interface MemoryPropagationGraph {
  root_memory_id: string;
  nodes: MemoryPropagationNode[];
  direct_contaminated: string[];
  indirect_contaminated: string[];
  suspected: string[];
  clean_boundary: string[];
}

export interface MemoryRollbackPayload {
  org_id: string;
  workspace: "governance" | "ops";
  operator_id: string;
  trace_id: string;
  root_memory_id: string;
  rollback_action: "delete" | "degrade" | "isolate" | "patch" | "branch";
  target_memory_ids: string[];
  reason: string;
  require_human_review?: boolean;
  propagation_graph?: Record<string, unknown> | null;
}

export interface MemoryRollbackResult {
  rollback_id: string;
  root_memory_id: string;
  action: string;
  affected_count: number;
  review_status: string;
  approval_id?: string | null;
  before_snapshot?: Record<string, unknown> | null;
  after_snapshot?: Record<string, unknown> | null;
}

export interface MemoryEvaluationPayload {
  org_id: string;
  workspace?: "governance";
  rollback_id: string;
  task_id?: string | null;
  trace_id?: string | null;
  scenario?: string | null;
}

export interface MemoryEvaluationResult {
  evaluation_id: string;
  rollback_id: string;
  scenario?: string | null;
  metrics?: Record<string, unknown> | null;
  replay_result?: Record<string, unknown> | null;
  conclusion?: string | null;
}

export interface MemoryPolicy {
  policy_key: string;
  policy_type: string;
  workspace: string;
  config?: Record<string, unknown> | null;
  status: string;
  version: number;
  updated_at?: string | null;
}

export interface MemoryPolicyUpsertPayload {
  workspace: "governance" | "ops" | "app";
  policy_type: "write_gate" | "retrieval" | "rollback" | "audit";
  config: Record<string, unknown>;
  status?: string;
}

export interface Approval {
  id: string;
  org_id: string;
  source_module: string;
  source_id?: string | null;
  operation_summary: string;
  risk_level: "low" | "medium" | "high" | "critical" | string;
  payload_json?: Record<string, unknown> | null;
  requester_id: string;
  requester_role: string;
  reviewer_id?: string | null;
  review_comment?: string | null;
  status: "pending" | "approved" | "rejected" | "cancelled" | string;
  created_at: string;
  reviewed_at?: string | null;
}

export interface ApprovalListQuery {
  page?: number;
  size?: number;
  status?: string;
  source_module?: string;
  risk_level?: string;
  requester_id?: string;
}

export interface InspectionStandardRagSpace {
  id: string;
  name: string;
  document_count: number;
  status?: string | null;
}

export interface InspectionStandardLibraryItem {
  id: string;
  org_id: string | null;
  name: string;
  product_family: string;
  description?: string | null;
  rag_space_ids: string[];
  rag_spaces: InspectionStandardRagSpace[];
  total_document_count: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface InspectionStandardPayload {
  name: string;
  product_family: string;
  description?: string | null;
  rag_space_ids: string[];
  is_active?: boolean;
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
  product_family: string | null;
  applicable_skus: string[] | null;
  required_views: string[] | null;
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
  product_family?: string | null;
  applicable_skus?: string[] | null;
  required_views?: string[] | null;
  required_image_count?: number;
  ai_gate_confidence_threshold?: number;
  ai_gate_evidence_threshold?: number;
  ai_gate_traceability_threshold?: number;
  auto_pass_enabled?: boolean;
  is_active?: boolean;
  items: InspectionSpecItemPayload[];
}
