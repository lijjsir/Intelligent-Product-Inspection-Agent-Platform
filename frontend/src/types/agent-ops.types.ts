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
}

export interface PromptDSPyConfig {
  id?: string;
  org_id?: string;
  prompt_version_id?: string;
  module_name: string;
  compiler_version?: string | null;
  fallback_prompt?: string | null;
  metric_names: string[];
  config_payload: Record<string, unknown>;
  is_enabled: boolean;
  updated_by?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface PromptOptimizationConfig {
  id?: string;
  target_key: string;
  subgraph_key: string;
  node_id: string;
  node_label: string;
  module_name: string;
  optimization_goal: string;
  optimizer_strategy: string;
  compiler_version?: string | null;
  metric_names: string[];
  config_payload: Record<string, unknown>;
  is_enabled: boolean;
  supports_compile: boolean;
  is_active_target: boolean;
  current_artifact_version?: string | null;
  previous_artifact_version?: string | null;
  latest_failed_artifact_version?: string | null;
  latest_error_message?: string | null;
  latest_metrics_snapshot?: Record<string, number> | null;
  last_compiled_at?: string | null;
  last_evaluated_at?: string | null;
  updated_by?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface PromptOptimizationConfigPayload {
  module_name: string;
  compiler_version?: string | null;
  optimizer_strategy: string;
  metric_names: string[];
  config_payload: Record<string, unknown>;
  is_enabled: boolean;
}

export interface PromptOptimizationRun {
  id: string;
  target_key: string;
  run_type: string;
  status: string;
  compiler_version?: string | null;
  artifact_version?: string | null;
  prompt_version_id?: string | null;
  metrics_snapshot?: Record<string, number> | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromptOptimizationGraphContext {
  focus_node_id: string;
  focus_node_label: string;
  upstream_nodes: string[];
  downstream_nodes: string[];
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface PromptOptimizationTarget {
  target_key: string;
  subgraph_key: string;
  node_id: string;
  node_label: string;
  module_name: string;
  optimization_goal: string;
  supports_compile: boolean;
  current_status: string;
  current_artifact_version?: string | null;
  latest_metrics?: Record<string, number> | null;
  graph_context: PromptOptimizationGraphContext;
  config: PromptOptimizationConfig;
  recent_runs: PromptOptimizationRun[];
}

export interface PromptOptimizationOverview {
  total_targets: number;
  enabled_targets: number;
  active_targets: number;
  successful_runs: number;
  failed_runs: number;
  pending_runs: number;
}

export interface PromptOptimizationTargetsResponse {
  overview: PromptOptimizationOverview;
  items: PromptOptimizationTarget[];
}

export interface PromptOptimizationTargetListQuery {
  page?: number;
  size?: number;
  subgraph_key?: string;
  status?: string;
  is_enabled?: boolean;
}

export interface PromptVersion {
  id: string;
  org_id: string;
  name: string;
  content: string;
  version: number;
  status: "draft" | "review" | "approved" | "deprecated";
  created_by: string | null;
  dspy_config?: PromptDSPyConfig | null;
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
  source_graph?: string | null;
  product_family?: string | null;
  product_id?: string | null;
  verdict?: string | null;
  expectation_matched?: boolean | null;
  top_sources: string[];
  rule_hits: string[];
  created_at: string;
}

export interface RagAnalysisResponse {
  stats: RagAnalysisStats;
  space_breakdown: RagAnalysisBreakdownItem[];
  source_graph_breakdown: RagAnalysisBreakdownItem[];
  product_family_breakdown: RagAnalysisBreakdownItem[];
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
}

export interface TopologyNode {
  id: string;
  label: string;
  kind: string;
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
