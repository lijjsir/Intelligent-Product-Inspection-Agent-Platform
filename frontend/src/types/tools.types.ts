export type ToolStatus = "draft" | "active" | "disabled" | "deprecated" | "deleted" | "error";
export type ToolCategory =
  | "RAG"
  | "file_parse"
  | "inspection_calc"
  | "report_gen"
  | "http_api"
  | "MCP"
  | "database";
export type ToolType = "native" | "http" | "rag" | "mcp" | "openapi";
export type RiskLevel = "low" | "medium" | "high";
export type SourceType = "builtin" | "manual" | "openapi" | "mcp";
export type HealthStatus = "healthy" | "degraded" | "unhealthy" | "unknown";
export type ToolExecutionStatus = "success" | "failed" | "timeout" | "running" | "pending";
export type ExecutionType = "runtime" | "test" | "health_check";
export type BindingStatus = "active" | "inactive";
export type ImportSource = "openapi" | "mcp" | "builtin_scan" | "manual_http";

export interface ToolDefinition {
  id: string;
  tool_key: string;
  display_name: string;
  description: string;
  category: ToolCategory;
  tool_type: ToolType;
  status: ToolStatus;
  risk_level: RiskLevel;
  is_readonly: boolean;
  source_type: SourceType;
  health_status: HealthStatus;
  active_version: string;
  bound_agent_names: string[];
  today_calls: number;
  success_rate: number;
  avg_latency_ms: number;
  created_at: string;
  updated_at: string;
}

export interface ToolDetail extends ToolDefinition {
  active_version_id: string;
  versions: ToolVersion[];
  executions: ToolExecutionRecord[];
  bindings: AgentToolBinding[];
  endpoint?: string;
  method?: string;
  handler_path?: string;
  parameters_schema: Record<string, unknown>;
  returns_schema: Record<string, unknown>;
  auth_type: string;
  secret_ref?: string;
  timeout_ms: number;
  retry_policy?: Record<string, unknown>;
  rate_limit_rpm: number;
  audit_logs: AuditLogEntry[];
}

export interface ToolVersion {
  id: string;
  tool_id: string;
  version: string;
  display_name: string;
  description: string;
  endpoint?: string;
  method?: string;
  handler_path?: string;
  parameters_schema: Record<string, unknown>;
  returns_schema: Record<string, unknown>;
  auth_type: string;
  timeout_ms: number;
  retry_policy?: Record<string, unknown>;
  rate_limit_rpm: number;
  status: ToolStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ToolExecutionRecord {
  id: string;
  tool_id: string;
  tool_name: string;
  agent_id: string;
  agent_name: string;
  task_id?: string;
  execution_type: ExecutionType;
  status: ToolExecutionStatus;
  duration_ms: number;
  input_summary: string;
  output_summary: string;
  error_message?: string;
  trace_id: string;
  created_at: string;
}

export interface AgentToolBinding {
  id: string;
  agent_id: string;
  agent_name: string;
  tool_id: string;
  tool_name: string;
  tool_version_id: string;
  tool_version: string;
  binding_status: BindingStatus;
  auto_call_enabled: boolean;
  approval_required: boolean;
  allowed_scenarios?: string[];
  rate_limit?: number;
  created_at: string;
  updated_at: string;
}

export interface AuditLogEntry {
  id: string;
  tool_id: string;
  action: string;
  operator: string;
  detail: string;
  created_at: string;
}

export interface TrendPoint {
  time: string;
  value: number;
}

export interface ToolFailureItem {
  tool_id: string;
  tool_name: string;
  failure_count: number;
  failure_rate: number;
}

export interface ToolLatencyItem {
  tool_id: string;
  tool_name: string;
  avg_latency_ms: number;
}

export interface ToolRiskItem {
  tool_id: string;
  tool_name: string;
  risk_level: RiskLevel;
}

export interface ToolCriticalDep {
  tool_id: string;
  tool_name: string;
  dependent_agents: number;
}

export interface ToolOverview {
  total_tools: number;
  active_tools: number;
  error_tools: number;
  today_calls: number;
  avg_latency_ms: number;
  high_risk_tools: number;
  call_trend: TrendPoint[];
  health_distribution: {
    healthy: number;
    degraded: number;
    unhealthy: number;
    unknown: number;
  };
  error_trend: TrendPoint[];
  top_failing: ToolFailureItem[];
  high_latency: ToolLatencyItem[];
  pending_risk_tools: ToolRiskItem[];
  critical_dependencies: ToolCriticalDep[];
}

export interface ToolListQuery {
  page?: number;
  size?: number;
  keyword?: string;
  category?: ToolCategory;
  status?: ToolStatus;
  risk_level?: RiskLevel;
  has_binding?: boolean;
  source_type?: SourceType;
  health_status?: HealthStatus;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}

export interface ToolBindingMatrix {
  agents: BindingAgentRow[];
  tools: BindingToolCol[];
}

export interface BindingAgentRow {
  agent_id: string;
  agent_name: string;
  bindings: Record<string, AgentToolBinding | null>;
}

export interface BindingToolCol {
  tool_id: string;
  tool_name: string;
  tool_key: string;
}

export interface ExecutionListQuery {
  page?: number;
  size?: number;
  tool_id?: string;
  agent_id?: string;
  status?: ToolExecutionStatus;
  execution_type?: ExecutionType;
}

export interface ExecutionOverview {
  today_calls: number;
  success_rate: number;
  avg_latency_ms: number;
  failed_count: number;
  call_trend: TrendPoint[];
  error_trend: TrendPoint[];
  latency_trend: TrendPoint[];
}

export interface ToolTestRequest {
  tool_id: string;
  params: Record<string, unknown>;
}

export interface ToolTestResult {
  status: ToolExecutionStatus;
  duration_ms: number;
  output: unknown;
  error?: string;
  trace_id: string;
}

export interface ToolCreateRequest {
  tool_key: string;
  display_name: string;
  description: string;
  category: ToolCategory;
  tool_type: ToolType;
  risk_level: RiskLevel;
  is_readonly: boolean;
  parameters_schema: Record<string, unknown>;
  returns_schema: Record<string, unknown>;
  endpoint?: string;
  method?: string;
  handler_path?: string;
  auth_type?: string;
  timeout_ms?: number;
  rate_limit_rpm?: number;
}

export interface ToolUpdateRequest {
  display_name?: string;
  description?: string;
  category?: ToolCategory;
  risk_level?: RiskLevel;
  is_readonly?: boolean;
}

export interface ToolVersionCreateRequest {
  display_name: string;
  description: string;
  version: string;
  parameters_schema?: Record<string, unknown>;
  returns_schema?: Record<string, unknown>;
  endpoint?: string;
  method?: string;
  handler_path?: string;
  auth_type?: string;
  timeout_ms?: number;
  rate_limit_rpm?: number;
}

export interface BindingCreateRequest {
  agent_id: string;
  tool_id: string;
  tool_version_id: string;
  auto_call_enabled?: boolean;
  approval_required?: boolean;
  allowed_scenarios?: string[];
  rate_limit?: number;
}

export interface BindingUpdateRequest {
  auto_call_enabled?: boolean;
  approval_required?: boolean;
  allowed_scenarios?: string[];
  rate_limit?: number;
}

export interface ToolSyncDetail {
  tool_key: string;
  action: "created" | "updated" | "unchanged";
}

export interface ToolSyncResult {
  created: number;
  updated: number;
  unchanged: number;
  details: ToolSyncDetail[];
}
