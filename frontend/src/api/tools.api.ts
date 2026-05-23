import { http } from "./http";
import type { PagedResponse } from "@/types/common.types";
import type {
  AgentToolBinding,
  BindingCreateRequest,
  BindingUpdateRequest,
  ExecutionListQuery,
  ExecutionOverview,
  ToolCreateRequest,
  ToolDefinition,
  ToolDetail,
  ToolExecutionRecord,
  ToolListQuery,
  ToolOverview,
  ToolSyncResult,
  ToolTestResult,
  ToolUpdateRequest,
  ToolVersion,
  ToolVersionCreateRequest,
} from "@/types/tools.types";

export const toolsApi = {
  async getOverview() {
    return http.get<ToolOverview>("/v1/tools/overview");
  },

  async listTools(query: ToolListQuery = {}) {
    return http.get<PagedResponse<ToolDefinition>>("/v1/tools", { params: query });
  },

  async getTool(id: string) {
    return http.get<ToolDetail>(`/v1/tools/${id}`);
  },

  async createTool(payload: ToolCreateRequest) {
    return http.post<ToolDefinition>("/v1/tools", payload);
  },

  async updateTool(id: string, payload: ToolUpdateRequest) {
    return http.put<ToolDefinition>(`/v1/tools/${id}`, payload);
  },

  async updateToolStatus(id: string, status: string) {
    return http.patch<ToolDefinition>(`/v1/tools/${id}/status`, { status });
  },

  async testTool(toolId: string, params: Record<string, unknown>) {
    return http.post<ToolTestResult>(`/v1/tools/${toolId}/test`, { params });
  },

  async listExecutions(query: ExecutionListQuery = {}) {
    return http.get<PagedResponse<ToolExecutionRecord>>("/v1/tools/executions", {
      params: query,
    });
  },

  async getExecutionOverview() {
    return http.get<ExecutionOverview>("/v1/tools/executions/overview");
  },

  async syncBuiltin() {
    return http.post<ToolSyncResult>("/v1/tools/sync/builtin");
  },

  async listVersions(toolId: string) {
    return http.get<ToolVersion[]>(`/v1/tools/${toolId}/versions`);
  },

  async createVersion(toolId: string, payload: ToolVersionCreateRequest) {
    return http.post<ToolVersion>(`/v1/tools/${toolId}/versions`, payload);
  },

  async publishVersion(toolId: string, versionId: string) {
    return http.post<{ success: boolean }>(
      `/v1/tools/${toolId}/versions/${versionId}/publish`,
    );
  },

  async rollbackVersion(toolId: string, versionId: string) {
    return http.post<{ success: boolean }>(
      `/v1/tools/${toolId}/versions/${versionId}/rollback`,
    );
  },

  async listBindings(toolId?: string) {
    return http.get<AgentToolBinding[]>("/v1/tools/bindings", {
      params: toolId ? { tool_id: toolId } : {},
    });
  },

  async createBinding(payload: BindingCreateRequest) {
    return http.post<AgentToolBinding>("/v1/tools/bindings", payload);
  },

  async updateBinding(id: string, payload: BindingUpdateRequest) {
    return http.put<AgentToolBinding>(`/v1/tools/bindings/${id}`, payload);
  },

  async deleteBinding(id: string) {
    return http.delete<{ deleted: boolean }>(`/v1/tools/bindings/${id}`);
  },
};
