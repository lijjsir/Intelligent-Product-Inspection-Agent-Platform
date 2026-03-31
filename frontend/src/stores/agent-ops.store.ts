import { defineStore } from "pinia";
import { ref } from "vue";
import { agentOpsApi } from "@/api/agent-ops.api";
import type {
  AgentDefinition,
  AgentDefinitionCreate,
  AgentDefinitionUpdate,
  AgentDefinitionListQuery,
  PromptVersion,
  PromptVersionCreate,
  PromptVersionUpdate,
  PromptVersionListQuery,
  IntentRoute,
  IntentRouteCreate,
  IntentRouteUpdate,
  IntentRouteListQuery,
  RagAnalysisResponse,
} from "@/types/agent-ops.types";

export const useAgentOpsStore = defineStore("agentOps", () => {
  const agents = ref<AgentDefinition[]>([]);
  const prompts = ref<PromptVersion[]>([]);
  const routes = ref<IntentRoute[]>([]);
  const ragAnalysis = ref<RagAnalysisResponse | null>(null);

  const agentsTotal = ref(0);
  const promptsTotal = ref(0);
  const routesTotal = ref(0);

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
    agentsTotal.value++;
    return data.data;
  }

  async function updateAgent(id: string, payload: AgentDefinitionUpdate) {
    const { data } = await agentOpsApi.updateAgent(id, payload);
    const idx = agents.value.findIndex((a) => a.id === id);
    if (idx !== -1) agents.value[idx] = data.data;
    return data.data;
  }

  async function deleteAgent(id: string) {
    await agentOpsApi.deleteAgent(id);
    agents.value = agents.value.filter((a) => a.id !== id);
    agentsTotal.value--;
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
    promptsTotal.value++;
    return data.data;
  }

  async function updatePrompt(id: string, payload: PromptVersionUpdate) {
    const { data } = await agentOpsApi.updatePrompt(id, payload);
    const idx = prompts.value.findIndex((p) => p.id === id);
    if (idx !== -1) prompts.value[idx] = data.data;
    return data.data;
  }

  async function deletePrompt(id: string) {
    await agentOpsApi.deletePrompt(id);
    prompts.value = prompts.value.filter((p) => p.id !== id);
    promptsTotal.value--;
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

  async function fetchRoute(id: string) {
    const { data } = await agentOpsApi.getRoute(id);
    return data.data;
  }

  async function createRoute(payload: IntentRouteCreate) {
    const { data } = await agentOpsApi.createRoute(payload);
    routes.value.unshift(data.data);
    routesTotal.value++;
    return data.data;
  }

  async function updateRoute(id: string, payload: IntentRouteUpdate) {
    const { data } = await agentOpsApi.updateRoute(id, payload);
    const idx = routes.value.findIndex((r) => r.id === id);
    if (idx !== -1) routes.value[idx] = data.data;
    return data.data;
  }

  async function deleteRoute(id: string) {
    await agentOpsApi.deleteRoute(id);
    routes.value = routes.value.filter((r) => r.id !== id);
    routesTotal.value--;
  }

  async function fetchRagAnalysis() {
    loading.value = true;
    try {
      const { data } = await agentOpsApi.getRagAnalysis();
      ragAnalysis.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  function $reset() {
    agents.value = [];
    prompts.value = [];
    routes.value = [];
    ragAnalysis.value = null;
    agentsTotal.value = 0;
    promptsTotal.value = 0;
    routesTotal.value = 0;
  }

  return {
    agents,
    prompts,
    routes,
    ragAnalysis,
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
    fetchRoutes,
    fetchRoute,
    createRoute,
    updateRoute,
    deleteRoute,
    fetchRagAnalysis,
    $reset,
  };
});
