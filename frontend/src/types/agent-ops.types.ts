export interface AgentDefinition {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  prompt_version_id: string | null;
  workflow_binding: string | null;
  intent_config_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentDefinitionCreate {
  name: string;
  description?: string;
  prompt_version_id?: string;
  workflow_binding?: string;
  intent_config_id?: string;
  is_active?: boolean;
}

export interface AgentDefinitionUpdate {
  name?: string;
  description?: string;
  prompt_version_id?: string;
  workflow_binding?: string;
  intent_config_id?: string;
  is_active?: boolean;
}

export interface AgentDefinitionListQuery {
  page?: number;
  size?: number;
  name?: string;
  is_active?: boolean;
}

export interface PromptVersion {
  id: string;
  org_id: string;
  name: string;
  content: string;
  version: number;
  status: 'draft' | 'review' | 'approved' | 'deprecated';
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

export interface RagAnalysisItem {
  task_id: string;
  query: string;
  hit_rate: number;
  citation_coverage: number;
  latency_ms: number;
  created_at: string;
}

export interface RagAnalysisResponse {
  stats: RagAnalysisStats;
  recent_items: RagAnalysisItem[];
}

export interface GraphNode {
  id: string;
  label: string;
  kind: string;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphOverview {
  selected_subgraph?: string;
  intent_name?: string;
  agent_name?: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface RouteSignal {
  key: string;
  label: string;
  description: string;
  source_stage: string;
}

export interface PriorityRule {
  order: number;
  when: string;
  target_subgraph: string;
  reason: string;
  examples?: string[];
  stop_on_match: boolean;
}

export interface DecisionCard {
  key: string;
  title: string;
  target_subgraph: string;
  reason: string;
  priority_order: number;
  matched_signals: string[];
  summary: string;
}

export interface SubgraphOverview {
  subgraph_key: string;
  label: string;
  summary: string;
  entry_node: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  typical_scenarios?: string[];
}

export interface RoutingStrategyOverview {
  route_mode: string;
  default_target: string;
  root_graph: GraphOverview;
  signals: RouteSignal[];
  priority_rules: PriorityRule[];
  decision_cards: DecisionCard[];
  subgraphs: SubgraphOverview[];
  registered_route_count: number;
  registered_intents: string[];
}
