import { http, type ApiEnvelope } from "./http";
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

interface PagedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export const agentOpsApi = {
  listAgents(query: AgentDefinitionListQuery) {
    return http.get<ApiEnvelope<PagedResponse<AgentDefinition>>>("/v1/agent-ops/agents", { params: query });
  },

  getAgent(id: string) {
    return http.get<ApiEnvelope<AgentDefinition>>(`/v1/agent-ops/agents/${id}`);
  },

  createAgent(payload: AgentDefinitionCreate) {
    return http.post<ApiEnvelope<AgentDefinition>>("/v1/agent-ops/agents", payload);
  },

  updateAgent(id: string, payload: AgentDefinitionUpdate) {
    return http.put<ApiEnvelope<AgentDefinition>>(`/v1/agent-ops/agents/${id}`, payload);
  },

  deleteAgent(id: string) {
    return http.delete<ApiEnvelope<{ deleted: boolean }>>(`/v1/agent-ops/agents/${id}`);
  },

  listPrompts(query: PromptVersionListQuery) {
    return http.get<ApiEnvelope<PagedResponse<PromptVersion>>>("/v1/agent-ops/prompts", { params: query });
  },

  getPrompt(id: string) {
    return http.get<ApiEnvelope<PromptVersion>>(`/v1/agent-ops/prompts/${id}`);
  },

  createPrompt(payload: PromptVersionCreate) {
    return http.post<ApiEnvelope<PromptVersion>>("/v1/agent-ops/prompts", payload);
  },

  updatePrompt(id: string, payload: PromptVersionUpdate) {
    return http.put<ApiEnvelope<PromptVersion>>(`/v1/agent-ops/prompts/${id}`, payload);
  },

  deletePrompt(id: string) {
    return http.delete<ApiEnvelope<{ deleted: boolean }>>(`/v1/agent-ops/prompts/${id}`);
  },

  listRoutes(query: IntentRouteListQuery) {
    return http.get<ApiEnvelope<PagedResponse<IntentRoute>>>("/v1/agent-ops/routes", { params: query });
  },

  getRoute(id: string) {
    return http.get<ApiEnvelope<IntentRoute>>(`/v1/agent-ops/routes/${id}`);
  },

  createRoute(payload: IntentRouteCreate) {
    return http.post<ApiEnvelope<IntentRoute>>("/v1/agent-ops/routes", payload);
  },

  updateRoute(id: string, payload: IntentRouteUpdate) {
    return http.put<ApiEnvelope<IntentRoute>>(`/v1/agent-ops/routes/${id}`, payload);
  },

  deleteRoute(id: string) {
    return http.delete<ApiEnvelope<{ deleted: boolean }>>(`/v1/agent-ops/routes/${id}`);
  },

  getRagAnalysis() {
    return http.get<ApiEnvelope<RagAnalysisResponse>>("/v1/agent-ops/rag-analysis");
  },
};
