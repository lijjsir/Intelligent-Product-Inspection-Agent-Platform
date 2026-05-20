import { http } from "./http";
import type {
  AgentDefinition,
  AgentDefinitionCreate,
  AgentDefinitionListQuery,
  AgentDefinitionUpdate,
  AgentRuntimeInstance,
  AgentRuntimeOverview,
  AgentTopology,
  IntentRoute,
  IntentRouteCreate,
  IntentRouteListQuery,
  IntentRouteUpdate,
  PromptVersion,
  PromptVersionCreate,
  PromptVersionListQuery,
  PromptVersionUpdate,
  AgentDetail,
  AgentRuntimeEvent,
  RagAnalysisResponse,
  RagTraceDetailResponse,
  RoutingStrategyOverview,
  RoutingCurrent,
  RouteSimulateRequest,
  RouteSimulateResult,
  RouteEventItem,
  RoutingMetrics,
} from "@/types/agent-ops.types";
import type { PagedResponse } from "@/types/common.types";

export const agentOpsApi = {
  listAgents(query: AgentDefinitionListQuery) {
    return http.get<PagedResponse<AgentDefinition>>("/v1/agent-ops/agents", { params: query });
  },

  getAgent(id: string) {
    return http.get<AgentDefinition>(`/v1/agent-ops/agents/${id}`);
  },

  createAgent(payload: AgentDefinitionCreate) {
    return http.post<AgentDefinition>("/v1/agent-ops/agents", payload);
  },

  updateAgent(id: string, payload: AgentDefinitionUpdate) {
    return http.put<AgentDefinition>(`/v1/agent-ops/agents/${id}`, payload);
  },

  deleteAgent(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/agent-ops/agents/${id}`);
  },

  listPrompts(query: PromptVersionListQuery) {
    return http.get<PagedResponse<PromptVersion>>("/v1/agent-ops/prompts", { params: query });
  },

  getPrompt(id: string) {
    return http.get<PromptVersion>(`/v1/agent-ops/prompts/${id}`);
  },

  createPrompt(payload: PromptVersionCreate) {
    return http.post<PromptVersion>("/v1/agent-ops/prompts", payload);
  },

  updatePrompt(id: string, payload: PromptVersionUpdate) {
    return http.put<PromptVersion>(`/v1/agent-ops/prompts/${id}`, payload);
  },

  deletePrompt(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/agent-ops/prompts/${id}`);
  },

  listRoutes(query: IntentRouteListQuery) {
    return http.get<PagedResponse<IntentRoute>>("/v1/agent-ops/routes", { params: query });
  },

  getRoutingStrategy() {
    return http.get<RoutingStrategyOverview>("/v1/agent-ops/routing/strategy");
  },

  getRoute(id: string) {
    return http.get<IntentRoute>(`/v1/agent-ops/routes/${id}`);
  },

  createRoute(payload: IntentRouteCreate) {
    return http.post<IntentRoute>("/v1/agent-ops/routes", payload);
  },

  updateRoute(id: string, payload: IntentRouteUpdate) {
    return http.put<IntentRoute>(`/v1/agent-ops/routes/${id}`, payload);
  },

  deleteRoute(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/agent-ops/routes/${id}`);
  },

  getRouteGraph(id: string) {
    return http.get<AgentTopology>(`/v1/agent-ops/routes/${id}/graph`);
  },

  getRagAnalysis() {
    return http.get<RagAnalysisResponse>("/v1/agent-ops/rag-analysis");
  },

  getRagTraceDetail(traceId: string) {
    return http.get<RagTraceDetailResponse>(
      `/v1/agent-ops/rag-analysis/traces/${encodeURIComponent(traceId)}`,
    );
  },

  getRuntimeOverview() {
    return http.get<AgentRuntimeOverview>("/v1/agent-ops/runtime/overview");
  },

  listRuntimeAgents() {
    return http.get<AgentRuntimeInstance[]>("/v1/agent-ops/runtime/agents");
  },

  startRuntimeAgent(runtimeKey: string) {
    return http.post<AgentRuntimeInstance>(
      `/v1/agent-ops/runtime/agents/${encodeURIComponent(runtimeKey)}/start`,
    );
  },

  stopRuntimeAgent(runtimeKey: string) {
    return http.post<AgentRuntimeInstance>(
      `/v1/agent-ops/runtime/agents/${encodeURIComponent(runtimeKey)}/stop`,
    );
  },

  getAgentsTopology(
    subgraphKey = "all",
    mode: "design" | "runtime" = "design",
    includePlanned = true,
  ) {
    return http.get<AgentTopology>("/v1/agent-ops/agents/topology", {
      params: { subgraph_key: subgraphKey, mode, include_planned: includePlanned },
    });
  },

  /** 暂停 Agent 路由 */
  pauseAgentRoute: (runtimeKey: string, data: { reason: string }) =>
    http.post<AgentRuntimeInstance>(`/v1/agent-ops/runtime/agents/${runtimeKey}/pause-route`, data),

  /** 恢复 Agent 路由 */
  resumeAgentRoute: (runtimeKey: string) =>
    http.post<AgentRuntimeInstance>(`/v1/agent-ops/runtime/agents/${runtimeKey}/resume-route`),

  /** 获取 Agent 完整详情 */
  getAgentDetail: (agentId: string) =>
    http.get<AgentDetail>(`/v1/agent-ops/agents/${agentId}/detail`),

  /** 查询 Agent 运行态事件 */
  getRuntimeEvents: (agentId: string, limit?: number) =>
    http.get<AgentRuntimeEvent[]>(`/v1/agent-ops/runtime/events`, { params: { agent_id: agentId, limit } }),

  /** ── Routing Strategy Viewer ── */

  getRoutingCurrent: () => http.get<RoutingCurrent>("/v1/agent-ops/routing/current"),
  simulateRoute: (data: RouteSimulateRequest) => http.post<RouteSimulateResult>("/v1/agent-ops/routing/simulate", data),
  getRoutingEvents: (limit?: number) => http.get<RouteEventItem[]>("/v1/agent-ops/routing/events", { params: { limit } }),
  getRoutingMetrics: () => http.get<RoutingMetrics>("/v1/agent-ops/routing/metrics"),
};
