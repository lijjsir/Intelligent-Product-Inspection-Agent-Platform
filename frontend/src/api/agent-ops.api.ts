import { http } from "./http";
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

  getRagAnalysis() {
    return http.get<RagAnalysisResponse>("/v1/agent-ops/rag-analysis");
  },
};
