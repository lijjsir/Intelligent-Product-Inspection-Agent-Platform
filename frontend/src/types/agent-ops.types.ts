/** Agent 产品接入状态 */
export type AgentLifecycleStatus =
  | "active"
  | "partial"
  | "planned"
  | "legacy"
  | "deprecated";

/** Agent 运行状态 */
export type AgentRuntimeStatus =
  | "running"
  | "stopped"
  | "degraded"
  | "maintenance"
  | "readonly";

/** Agent 分组 */
export type AgentGroup = "core" | "memory" | "planned" | "legacy";

export interface AgentMetricsSummary {
  execution_count?: number;
  success_count?: number;
  success_rate?: number;
  avg_latency_ms?: number;
  last_executed_at?: string | null;
}

export interface AgentDefinition {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  prompt_version_id: string | null;
  workflow_binding: string | null;
  intent_config_id: string | null;
  subgraph_key: string;
  entry_graph: string | null;
  supports_start_stop: boolean;
  graph_version: string;
  is_active: boolean;
  runtime_status?: string | null;
  metrics_summary?: AgentMetricsSummary | null;
  /** 产品接入状态 */
  lifecycle_status: AgentLifecycleStatus;
  /** 分组 */
  group_key: AgentGroup;
  /** 是否参与路由 */
  route_enabled: boolean;
  /** 是否允许暂停恢复路由 */
  supports_route_toggle: boolean;
  /** 给客户看的能力说明 */
  customer_visible_description?: string;
  created_at: string;
  updated_at: string;
}

export interface AgentDefinitionCreate {
  name: string;
  description?: string;
  prompt_version_id?: string;
  workflow_binding?: string;
  intent_config_id?: string;
  subgraph_key?: string;
  entry_graph?: string;
  supports_start_stop?: boolean;
  graph_version?: string;
  is_active?: boolean;
}

export interface AgentDefinitionUpdate {
  name?: string;
  description?: string;
  prompt_version_id?: string;
  workflow_binding?: string;
  intent_config_id?: string;
  subgraph_key?: string;
  entry_graph?: string;
  supports_start_stop?: boolean;
  graph_version?: string;
  is_active?: boolean;
}

export interface AgentDefinitionListQuery {
  page?: number;
  size?: number;
  name?: string;
  is_active?: boolean;
  group_key?: string;
  lifecycle_status?: string;
}

export interface PromptVersion {
  id: string;
  org_id: string;
  name: string;
  content: string;
  version: number;
  status: "draft" | "review" | "approved" | "deprecated";
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromptVersionCreate {
  name: string;
  content: string;
  version?: number;
  status?: string;
}

export interface PromptVersionUpdate {
  name?: string;
  content?: string;
  version?: number;
  status?: string;
}

export interface PromptVersionListQuery {
  page?: number;
  size?: number;
  name?: string;
  status?: string;
}

export interface IntentRoute {
  id: string;
  org_id: string;
  intent_name: string;
  agent_id: string | null;
  priority: number;
  sample_count: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface IntentRouteCreate {
  intent_name: string;
  agent_id?: string;
  priority?: number;
  sample_count?: number;
  is_active?: boolean;
}

export interface IntentRouteUpdate {
  intent_name?: string;
  agent_id?: string;
  priority?: number;
  sample_count?: number;
  is_active?: boolean;
}

export interface IntentRouteListQuery {
  page?: number;
  size?: number;
  intent_name?: string;
  is_active?: boolean;
}

export interface RagAnalysisStats {
  total_queries: number;
  avg_hit_rate: number;
  avg_citation_coverage: number;
  empty_recall_count: number;
  avg_latency_ms: number;
}

export interface RagAnalysisBreakdownItem {
  key: string;
  label: string;
  value: number;
  avg_hit_rate: number;
  avg_citation_coverage: number;
}

export interface RagAnalysisOption {
  key: string;
  label: string;
}

export interface RagEvidenceImpactItem {
  rule_key: string;
  verdicts: string[];
  source_count: number;
  query_count: number;
  sources: string[];
}

export interface RagAnalysisItem {
  task_id: string;
  session_id?: string | null;
  query?: string | null;
  rag_space_id?: string | null;
  rag_space_name?: string | null;
  hit_count: number;
  hit_rate: number;
  citation_coverage: number;
  latency_ms: number;
  source_agent?: string | null;
  source_graph?: string | null;
  sub_route?: string | null;
  trace_id?: string | null;
  top_score?: number | null;
  product_id?: string | null;
  verdict?: string | null;
  expectation_matched?: boolean | null;
  evidence_found: boolean;
  evidence_used: boolean;
  verdict_impacted: boolean;
  top_sources: string[];
  rule_hits: string[];
  created_at: string;
}

export interface RagTraceDetailResponse {
  trace_id: string;
  query?: string | null;
  rag_space_id?: string | null;
  rag_space_name?: string | null;
  source_agent?: string | null;
  source_graph?: string | null;
  sub_route?: string | null;
  top_k: number;
  hit_count: number;
  hit_rate: number;
  citation_coverage: number;
  latency_ms: number;
  top_score?: number | null;
  product_family?: string | null;
  expectation_matched?: boolean | null;
  evidence_found: boolean;
  evidence_used: boolean;
  verdict_impacted: boolean;
  retrieval_config: Record<string, unknown>;
  retrieved_chunks: Record<string, unknown>[];
  used_citations: Record<string, unknown>[];
  rule_hits: string[];
  verdict?: string | null;
  answer?: string | null;
  result?: unknown;
  top_sources: string[];
  created_at?: string | null;
}

export interface RagAnalysisResponse {
  stats: RagAnalysisStats;
  space_options: RagAnalysisOption[];
  source_agent_options: RagAnalysisOption[];
  space_breakdown: RagAnalysisBreakdownItem[];
  source_agent_breakdown: RagAnalysisBreakdownItem[];
  evidence_impact: RagEvidenceImpactItem[];
  recent_items: RagAnalysisItem[];
}

export interface AgentRuntimeOverview {
  active_agents: number;
  running_agents: number;
  stopped_agents: number;
  total_executions: number;
  avg_latency_ms: number;
  queued_tasks: number;
  completed_today: number;
  /** 成功率 */
  success_rate: number;
  /** 最近错误数 */
  recent_errors: number;
}

export interface AgentRuntimeInstance {
  runtime_key: string;
  agent_id: string;
  agent_name: string;
  subgraph_key: string;
  status: string;
  supports_start_stop: boolean;
  is_active: boolean;
  execution_count: number;
  success_rate: number;
  avg_latency_ms: number;
  last_executed_at?: string | null;
  last_started_at?: string | null;
  last_stopped_at?: string | null;
  /** 运行时状态 */
  runtime_status: AgentRuntimeStatus;
  /** 产品接入状态 */
  lifecycle_status?: AgentLifecycleStatus;
  /** 分组 */
  group_key?: AgentGroup;
  /** 是否参与路由 */
  route_enabled: boolean;
  /** 是否允许暂停恢复路由 */
  supports_route_toggle: boolean;
  /** 客户能力说明 */
  customer_visible_description?: string;
  /** 最近错误信息 */
  last_error_message?: string;
  /** 维护原因 */
  maintenance_reason?: string;
}

export interface TopologyNode {
  id: string;
  label: string;
  kind: string;
  subgraph_key?: string;
  agent_name?: string;
  /** 运行时状态（用于着色） */
  status?: AgentRuntimeStatus;
  /** 产品状态 */
  lifecycle_status?: AgentLifecycleStatus;
  /** 是否参与路由 */
  route_enabled?: boolean;
  /** 执行次数 */
  execution_count?: number;
  /** 平均延迟 */
  avg_latency_ms?: number;
  /** 最近启动时间 */
  last_started_at?: string | null;
  /** 错误率 */
  error_rate?: number;
}

export interface TopologyEdge {
  source: string;
  target: string;
}

export interface AgentTopology {
  selected_subgraph: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  intent_name?: string | null;
  agent_name?: string | null;
}

export interface RoutingSignalDescriptor {
  key: string;
  label: string;
  description: string;
  source_stage: string;
}

export interface RoutingPriorityRule {
  order: number;
  when: string;
  target_subgraph: string;
  reason: string;
  examples: string[];
  stop_on_match: boolean;
}

export interface RoutingDecisionCard {
  key: string;
  title: string;
  target_subgraph: string;
  reason: string;
  priority_order: number;
  matched_signals: string[];
  summary: string;
}

export interface RoutingSubgraphDescriptor {
  subgraph_key: string;
  label: string;
  summary: string;
  entry_node: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  typical_scenarios: string[];
}

export interface RoutingStrategyOverview {
  route_mode: string;
  default_target: string;
  root_graph: AgentTopology;
  subgraphs: RoutingSubgraphDescriptor[];
  priority_rules: RoutingPriorityRule[];
  signals: RoutingSignalDescriptor[];
  decision_cards: RoutingDecisionCard[];
  registered_route_count: number;
  registered_intents: string[];
}

/** Agent 运行态事件 */
export interface AgentRuntimeEvent {
  id: string;
  agent_id: string;
  runtime_key: string;
  event_type: "pause_route" | "resume_route" | "start" | "stop" | "maintenance";
  before_status?: string;
  after_status?: string;
  reason?: string;
  operator_id?: string;
  created_at: string;
}

/** Agent 详情（含绑定资源和操作记录） */
export interface AgentDetail extends AgentDefinition {
  bound_prompt_version?: PromptVersion;
  bound_routes: IntentRoute[];
  runtime_events: AgentRuntimeEvent[];
}

/** 暂停路由请求 */
export interface PauseRouteRequest {
  reason: string;
}

/** ── Routing Strategy Viewer types ── */

export interface RouteAgentDescriptor {
  key: string;
  label: string;
  sub_routes: string[];
}

export interface RouteRuleDescriptor {
  priority: number;
  name: string;
  condition_summary: string;
  target_agent: string;
  target_sub_route: string;
  route_source: string;
  examples: string[];
}

export interface RouteSignalInfo {
  key: string;
  label: string;
  description: string;
  detected: boolean;
}

export interface ManagerIntentDescriptor {
  priority: number;
  name: string;
  condition: string;
  intent: string;
  target_agent: string;
  needs: string[];
  risk: string;
  description: string;
}

export interface RoutingCurrent {
  mode: string;
  mode_label: string;
  default_agent: string;
  default_sub_route: string;
  agents: RouteAgentDescriptor[];
  manager_intents: ManagerIntentDescriptor[];
  rules: RouteRuleDescriptor[];
  signals: RouteSignalInfo[];
  rule_count: number;
  active_agent_count: number;
}

export interface RouteSimulateRequest {
  query: string;
  has_image: boolean;
  has_structured_file: boolean;
  has_rag_space: boolean;
}

export interface RouteSimulateResult {
  matched_rule_name: string;
  matched_priority: number;
  selected_agent: string;
  selected_sub_route: string;
  route_source: string;
  reason: string;
  signals: Record<string, boolean>;
  is_fallback: boolean;
}

export interface RouteEventItem {
  id: string;
  created_at: string;
  selected_agent: string;
  sub_route?: string;
  route_source: string;
  reason?: string;
  intent_name?: string;
  confidence: number;
  latency_ms: number;
  blocked: boolean;
  blocked_reason?: string;
  request_summary?: string;
}

export interface RoutingMetrics {
  total_24h: number;
  rule_hit_count: number;
  model_fallback_count: number;
  blocked_count: number;
  avg_latency_ms: number;
  by_agent: Record<string, number>;
  by_rule: Record<string, number>;
}
