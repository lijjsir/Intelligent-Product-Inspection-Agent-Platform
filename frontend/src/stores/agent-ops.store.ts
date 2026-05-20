import { defineStore } from "pinia";
import { ref } from "vue";
import { agentOpsApi } from "@/api/agent-ops.api";
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
  PromptDSPyConfig,
  PromptOptimizationConfigPayload,
  PromptOptimizationRun,
  PromptOptimizationTarget,
  PromptOptimizationTargetListQuery,
  PromptOptimizationTargetsResponse,
  PromptVersion,
  PromptVersionCreate,
  PromptVersionListQuery,
  PromptVersionUpdate,
  AgentDetail,
  AgentRuntimeEvent,
  PauseRouteRequest,
  RagAnalysisResponse,
  RagTraceDetailResponse,
  RoutingStrategyOverview,
  RoutingCurrent,
  RouteSimulateRequest,
  RouteSimulateResult,
  RouteEventItem,
  RoutingMetrics,
} from "@/types/agent-ops.types";

export const useAgentOpsStore = defineStore("agentOps", () => {
  const agents = ref<AgentDefinition[]>([]);
  const prompts = ref<PromptVersion[]>([]);
  const routes = ref<IntentRoute[]>([]);
  const ragAnalysis = ref<RagAnalysisResponse | null>(null);
  const ragTraceDetail = ref<RagTraceDetailResponse | null>(null);
  const ragTraceDetailLoading = ref(false);
  const runtimeOverview = ref<AgentRuntimeOverview | null>(null);
  const runtimeAgents = ref<AgentRuntimeInstance[]>([]);
  const topology = ref<AgentTopology | null>(null);
  const routeTopology = ref<AgentTopology | null>(null);
  const routingStrategy = ref<RoutingStrategyOverview | null>(null);
  const promptOptimization = ref<PromptOptimizationTargetsResponse | null>(null);
  const promptOptimizationCurrent = ref<PromptOptimizationTarget | null>(null);
  const promptOptimizationRuns = ref<PromptOptimizationRun[]>([]);

  const agentsTotal = ref(0);
  const promptsTotal = ref(0);
  const routesTotal = ref(0);

  /** Agent 详情 */
  const agentDetail = ref<AgentDetail | null>(null);
  /** 运行态事件列表 */
  const runtimeEvents = ref<AgentRuntimeEvent[]>([]);

  /** ── Routing Strategy Viewer state ── */
  const routingCurrent = ref<RoutingCurrent | null>(null);
  const simulateResult = ref<RouteSimulateResult | null>(null);
  const routingEvents = ref<RouteEventItem[]>([]);
  const routingMetrics = ref<RoutingMetrics | null>(null);

  const loading = ref(false);

  async function fetchAgents(query: AgentDefinitionListQuery) {
    loading.value = true;
    try {
      const { data } = await agentOpsApi.listAgents(query);
      agents.value = data.data.items;
      agentsTotal.value = data.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function fetchAgent(id: string) {
    const { data } = await agentOpsApi.getAgent(id);
    return data.data;
  }

  async function createAgent(payload: AgentDefinitionCreate) {
    const { data } = await agentOpsApi.createAgent(payload);
    agents.value.unshift(data.data);
    agentsTotal.value += 1;
    return data.data;
  }

  async function updateAgent(id: string, payload: AgentDefinitionUpdate) {
    const { data } = await agentOpsApi.updateAgent(id, payload);
    const idx = agents.value.findIndex((item) => item.id === id);
    if (idx !== -1) agents.value[idx] = data.data;
    return data.data;
  }

  async function deleteAgent(id: string) {
    await agentOpsApi.deleteAgent(id);
    agents.value = agents.value.filter((item) => item.id !== id);
    agentsTotal.value = Math.max(0, agentsTotal.value - 1);
  }

  async function fetchPrompts(query: PromptVersionListQuery) {
    loading.value = true;
    try {
      const { data } = await agentOpsApi.listPrompts(query);
      prompts.value = data.data.items;
      promptsTotal.value = data.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function fetchPrompt(id: string) {
    const { data } = await agentOpsApi.getPrompt(id);
    return data.data;
  }

  async function createPrompt(payload: PromptVersionCreate) {
    const { data } = await agentOpsApi.createPrompt(payload);
    prompts.value.unshift(data.data);
    promptsTotal.value += 1;
    return data.data;
  }

  async function updatePrompt(id: string, payload: PromptVersionUpdate) {
    const { data } = await agentOpsApi.updatePrompt(id, payload);
    const idx = prompts.value.findIndex((item) => item.id === id);
    if (idx !== -1) prompts.value[idx] = data.data;
    return data.data;
  }

  async function deletePrompt(id: string) {
    await agentOpsApi.deletePrompt(id);
    prompts.value = prompts.value.filter((item) => item.id !== id);
    promptsTotal.value = Math.max(0, promptsTotal.value - 1);
  }

  async function fetchPromptDspy(id: string) {
    const { data } = await agentOpsApi.getPromptDspy(id);
    return data.data;
  }

  async function savePromptDspy(id: string, payload: PromptDSPyConfig) {
    const { data } = await agentOpsApi.updatePromptDspy(id, payload);
    const idx = prompts.value.findIndex((item) => item.id === id);
    if (idx !== -1) {
      prompts.value[idx] = {
        ...prompts.value[idx],
        dspy_config: data.data,
      };
    }
    return data.data;
  }

  async function fetchPromptOptimizationTargets(query: PromptOptimizationTargetListQuery = {}) {
    loading.value = true;
    try {
      const { data } = await agentOpsApi.listPromptOptimizationTargets(query);
      promptOptimization.value = data.data;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchPromptOptimizationTarget(targetKey: string) {
    const { data } = await agentOpsApi.getPromptOptimizationTarget(targetKey);
    promptOptimizationCurrent.value = data.data;
    return data.data;
  }

  async function updatePromptOptimizationConfig(targetKey: string, payload: PromptOptimizationConfigPayload) {
    const { data } = await agentOpsApi.updatePromptOptimizationConfig(targetKey, payload);
    if (promptOptimizationCurrent.value?.target_key === targetKey) {
      promptOptimizationCurrent.value = {
        ...promptOptimizationCurrent.value,
        config: data.data,
      };
    }
    if (promptOptimization.value) {
      promptOptimization.value.items = promptOptimization.value.items.map((item) =>
        item.target_key === targetKey ? { ...item, config: data.data } : item,
      );
    }
    return data.data;
  }

  async function compilePromptOptimizationTarget(targetKey: string) {
    const { data } = await agentOpsApi.compilePromptOptimizationTarget(targetKey);
    return data.data;
  }

  async function fetchPromptOptimizationRuns(targetKey: string) {
    const { data } = await agentOpsApi.listPromptOptimizationRuns(targetKey);
    promptOptimizationRuns.value = data.data;
    return data.data;
  }

  async function rollbackPromptOptimizationTarget(targetKey: string) {
    const { data } = await agentOpsApi.rollbackPromptOptimizationTarget(targetKey);
    return data.data;
  }

  async function fetchRoutes(query: IntentRouteListQuery) {
    loading.value = true;
    try {
      const { data } = await agentOpsApi.listRoutes(query);
      routes.value = data.data.items;
      routesTotal.value = data.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function fetchRoutingStrategy() {
    loading.value = true;
    try {
      const { data } = await agentOpsApi.getRoutingStrategy();
      routingStrategy.value = data.data;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchRoute(id: string) {
    const { data } = await agentOpsApi.getRoute(id);
    return data.data;
  }

  async function createRoute(payload: IntentRouteCreate) {
    const { data } = await agentOpsApi.createRoute(payload);
    routes.value.unshift(data.data);
    routesTotal.value += 1;
    return data.data;
  }

  async function updateRoute(id: string, payload: IntentRouteUpdate) {
    const { data } = await agentOpsApi.updateRoute(id, payload);
    const idx = routes.value.findIndex((item) => item.id === id);
    if (idx !== -1) routes.value[idx] = data.data;
    return data.data;
  }

  async function deleteRoute(id: string) {
    await agentOpsApi.deleteRoute(id);
    routes.value = routes.value.filter((item) => item.id !== id);
    routesTotal.value = Math.max(0, routesTotal.value - 1);
  }

  async function fetchRouteGraph(id: string) {
    const { data } = await agentOpsApi.getRouteGraph(id);
    routeTopology.value = data.data;
    return data.data;
  }

  async function fetchRagAnalysis(options?: { silent?: boolean }) {
    if (!options?.silent) {
      loading.value = true;
    }
    try {
      const { data } = await agentOpsApi.getRagAnalysis();
      ragAnalysis.value = data.data;
    } finally {
      if (!options?.silent) {
        loading.value = false;
      }
    }
  }

  async function fetchRagTraceDetail(traceId: string) {
    ragTraceDetailLoading.value = true;
    try {
      const { data } = await agentOpsApi.getRagTraceDetail(traceId);
      ragTraceDetail.value = data.data;
      return data.data;
    } finally {
      ragTraceDetailLoading.value = false;
    }
  }

  async function fetchRuntimeOverview() {
    const { data } = await agentOpsApi.getRuntimeOverview();
    runtimeOverview.value = data.data;
    return data.data;
  }

  async function fetchRuntimeAgents() {
    const { data } = await agentOpsApi.listRuntimeAgents();
    runtimeAgents.value = data.data;
    return data.data;
  }

  async function startRuntimeAgent(runtimeKey: string) {
    const { data } = await agentOpsApi.startRuntimeAgent(runtimeKey);
    const idx = runtimeAgents.value.findIndex((item) => item.runtime_key === runtimeKey);
    if (idx !== -1) runtimeAgents.value[idx] = data.data;
    const agentIdx = agents.value.findIndex((item) => item.id === data.data.agent_id);
    if (agentIdx !== -1) {
      agents.value[agentIdx] = { ...agents.value[agentIdx], runtime_status: data.data.runtime_status };
    }
    return data.data;
  }

  async function stopRuntimeAgent(runtimeKey: string) {
    const { data } = await agentOpsApi.stopRuntimeAgent(runtimeKey);
    const idx = runtimeAgents.value.findIndex((item) => item.runtime_key === runtimeKey);
    if (idx !== -1) runtimeAgents.value[idx] = data.data;
    const agentIdx = agents.value.findIndex((item) => item.id === data.data.agent_id);
    if (agentIdx !== -1) {
      agents.value[agentIdx] = { ...agents.value[agentIdx], runtime_status: data.data.runtime_status };
    }
    return data.data;
  }

  async function fetchAgentsTopology(
    subgraphKey = "all",
    mode: "design" | "runtime" = "design",
    includePlanned = true,
  ) {
    const { data } = await agentOpsApi.getAgentsTopology(subgraphKey, mode, includePlanned);
    topology.value = data.data;
    return data.data;
  }

  /** 暂停路由 */
  async function pauseRoute(runtimeKey: string, reason: string) {
    const { data } = await agentOpsApi.pauseAgentRoute(runtimeKey, { reason });
    const runtimeIdx = runtimeAgents.value.findIndex((item) => item.runtime_key === runtimeKey);
    if (runtimeIdx !== -1) runtimeAgents.value[runtimeIdx] = data.data;
    const agentIdx = agents.value.findIndex((item) => item.id === data.data.agent_id);
    if (agentIdx !== -1) {
      agents.value[agentIdx] = {
        ...agents.value[agentIdx],
        route_enabled: data.data.route_enabled,
        runtime_status: data.data.runtime_status,
      };
    }
    if (agentDetail.value?.id === data.data.agent_id) {
      agentDetail.value = {
        ...agentDetail.value,
        route_enabled: data.data.route_enabled,
        runtime_status: data.data.runtime_status,
      };
    }
    return data.data;
  }

  /** 恢复路由 */
  async function resumeRoute(runtimeKey: string) {
    const { data } = await agentOpsApi.resumeAgentRoute(runtimeKey);
    const runtimeIdx = runtimeAgents.value.findIndex((item) => item.runtime_key === runtimeKey);
    if (runtimeIdx !== -1) runtimeAgents.value[runtimeIdx] = data.data;
    const agentIdx = agents.value.findIndex((item) => item.id === data.data.agent_id);
    if (agentIdx !== -1) {
      agents.value[agentIdx] = {
        ...agents.value[agentIdx],
        route_enabled: data.data.route_enabled,
        runtime_status: data.data.runtime_status,
      };
    }
    if (agentDetail.value?.id === data.data.agent_id) {
      agentDetail.value = {
        ...agentDetail.value,
        route_enabled: data.data.route_enabled,
        runtime_status: data.data.runtime_status,
      };
    }
    return data.data;
  }

  /** 获取 Agent 详情 */
  async function fetchAgentDetail(agentId: string) {
    const { data } = await agentOpsApi.getAgentDetail(agentId);
    agentDetail.value = data.data;
  }

  /** 获取运行态事件 */
  async function fetchRuntimeEvents(agentId: string, limit = 20) {
    const { data } = await agentOpsApi.getRuntimeEvents(agentId, limit);
    runtimeEvents.value = data.data;
  }

  /** ── Routing Strategy Viewer actions ── */

  async function fetchRoutingCurrent() {
    const { data } = await agentOpsApi.getRoutingCurrent();
    routingCurrent.value = data.data;
  }

  async function simulateRoute(simData: RouteSimulateRequest) {
    const { data } = await agentOpsApi.simulateRoute(simData);
    simulateResult.value = data.data;
  }

  async function fetchRoutingEvents(limit = 20) {
    const { data } = await agentOpsApi.getRoutingEvents(limit);
    routingEvents.value = data.data;
  }

  async function fetchRoutingMetrics() {
    const { data } = await agentOpsApi.getRoutingMetrics();
    routingMetrics.value = data.data;
  }

  function $reset() {
    agents.value = [];
    prompts.value = [];
    routes.value = [];
    ragAnalysis.value = null;
    ragTraceDetail.value = null;
    ragTraceDetailLoading.value = false;
    runtimeOverview.value = null;
    runtimeAgents.value = [];
    topology.value = null;
    routeTopology.value = null;
    routingStrategy.value = null;
    promptOptimization.value = null;
    promptOptimizationCurrent.value = null;
    promptOptimizationRuns.value = [];
    agentDetail.value = null;
    runtimeEvents.value = [];
    routingCurrent.value = null;
    simulateResult.value = null;
    routingEvents.value = [];
    routingMetrics.value = null;
    agentsTotal.value = 0;
    promptsTotal.value = 0;
    routesTotal.value = 0;
  }

  return {
    agents,
    prompts,
    routes,
    ragAnalysis,
    ragTraceDetail,
    ragTraceDetailLoading,
    runtimeOverview,
    runtimeAgents,
    topology,
    routeTopology,
    routingStrategy,
    promptOptimization,
    promptOptimizationCurrent,
    promptOptimizationRuns,
    agentDetail,
    runtimeEvents,
    routingCurrent,
    simulateResult,
    routingEvents,
    routingMetrics,
    agentsTotal,
    promptsTotal,
    routesTotal,
    loading,
    fetchAgents,
    fetchAgent,
    createAgent,
    updateAgent,
    deleteAgent,
    fetchPrompts,
    fetchPrompt,
    createPrompt,
    updatePrompt,
    deletePrompt,
    fetchPromptDspy,
    savePromptDspy,
    fetchPromptOptimizationTargets,
    fetchPromptOptimizationTarget,
    updatePromptOptimizationConfig,
    compilePromptOptimizationTarget,
    fetchPromptOptimizationRuns,
    rollbackPromptOptimizationTarget,
    fetchRoutes,
    fetchRoutingStrategy,
    fetchRoute,
    createRoute,
    updateRoute,
    deleteRoute,
    fetchRouteGraph,
    fetchRagAnalysis,
    fetchRagTraceDetail,
    fetchRuntimeOverview,
    fetchRuntimeAgents,
    startRuntimeAgent,
    stopRuntimeAgent,
    fetchAgentsTopology,
    pauseRoute,
    resumeRoute,
    fetchAgentDetail,
    fetchRuntimeEvents,
    fetchRoutingCurrent,
    simulateRoute,
    fetchRoutingEvents,
    fetchRoutingMetrics,
    $reset,
  };
});
