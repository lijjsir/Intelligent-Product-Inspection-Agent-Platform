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
import {
  mockExecutionOverview,
  mockExecutions,
  mockToolDetail,
  mockToolOverview,
  mockToolTest,
  mockTools,
} from "./tools.mock";

type Envelope<T> = {
  code: number;
  message: string;
  data: T;
};

type Wrapped<T> = {
  data: Envelope<T>;
};

const USE_MOCK = import.meta.env.VITE_TOOLS_USE_MOCK === "true";
const USE_PREVIEW_MOCKS = import.meta.env.VITE_TOOLS_USE_PREVIEW_MOCKS === "true";

export const toolsFeatureFlags = {
  coreMock: USE_MOCK,
  previewMocks: USE_PREVIEW_MOCKS,
};

function delay<T>(data: T, ms = 200): Promise<T> {
  return new Promise((resolve) => window.setTimeout(() => resolve(data), ms));
}

function wrap<T>(data: T): Wrapped<T> {
  return { data: { code: 0, message: "ok", data } };
}

export const toolsApi = {
  async getOverview(): Promise<Wrapped<ToolOverview>> {
    if (USE_MOCK) return delay(wrap(mockToolOverview()));
    return http.get<ToolOverview>("/v1/tools/overview") as Promise<Wrapped<ToolOverview>>;
  },

  async listTools(query: ToolListQuery = {}): Promise<Wrapped<PagedResponse<ToolDefinition>>> {
    if (USE_MOCK) {
      const keyword = query.keyword?.trim().toLowerCase();
      let items = [...mockTools];

      if (keyword) {
        items = items.filter((tool) =>
          [tool.display_name, tool.tool_key, tool.description].some((value) =>
            value.toLowerCase().includes(keyword),
          ),
        );
      }

      if (query.category) items = items.filter((tool) => tool.category === query.category);
      if (query.status) items = items.filter((tool) => tool.status === query.status);
      if (query.risk_level) items = items.filter((tool) => tool.risk_level === query.risk_level);
      if (query.source_type) items = items.filter((tool) => tool.source_type === query.source_type);
      if (query.health_status) items = items.filter((tool) => tool.health_status === query.health_status);
      if (query.has_binding !== undefined) {
        items = items.filter((tool) =>
          query.has_binding ? tool.bound_agent_names.length > 0 : tool.bound_agent_names.length === 0,
        );
      }

      const page = query.page ?? 1;
      const size = query.size ?? 12;
      const start = (page - 1) * size;

      return delay(
        wrap({
          items: items.slice(start, start + size),
          total: items.length,
          page,
          size,
        }),
      );
    }

    return http.get<PagedResponse<ToolDefinition>>("/v1/tools", { params: query }) as Promise<
      Wrapped<PagedResponse<ToolDefinition>>
    >;
  },

  async getTool(id: string): Promise<Wrapped<ToolDetail>> {
    if (USE_MOCK) return delay(wrap(mockToolDetail(id)));
    return http.get<ToolDetail>(`/v1/tools/${id}`) as Promise<Wrapped<ToolDetail>>;
  },

  async createTool(payload: ToolCreateRequest): Promise<Wrapped<ToolDefinition>> {
    if (USE_MOCK) return delay(wrap(mockTools[0]), 300);
    return http.post<ToolDefinition>("/v1/tools", payload) as Promise<Wrapped<ToolDefinition>>;
  },

  async updateTool(id: string, payload: ToolUpdateRequest): Promise<Wrapped<ToolDefinition>> {
    if (USE_MOCK) return delay(wrap({ ...mockTools[0], ...payload }), 300);
    return http.put<ToolDefinition>(`/v1/tools/${id}`, payload) as Promise<Wrapped<ToolDefinition>>;
  },

  async updateToolStatus(id: string, status: string): Promise<Wrapped<ToolDefinition>> {
    if (USE_MOCK) {
      return delay(wrap({ ...mockTools[0], status: status as ToolDefinition["status"] }), 300);
    }

    return http.patch<ToolDefinition>(`/v1/tools/${id}/status`, { status }) as Promise<
      Wrapped<ToolDefinition>
    >;
  },

  async testTool(toolId: string, params: Record<string, unknown>): Promise<Wrapped<ToolTestResult>> {
    if (USE_MOCK) return delay(wrap(mockToolTest()), 500);
    return http.post<ToolTestResult>(`/v1/tools/${toolId}/test`, { params }) as Promise<
      Wrapped<ToolTestResult>
    >;
  },

  async listExecutions(
    query: ExecutionListQuery = {},
  ): Promise<Wrapped<PagedResponse<ToolExecutionRecord>>> {
    if (USE_MOCK) {
      let items = [...mockExecutions];

      if (query.tool_id) items = items.filter((item) => item.tool_id === query.tool_id);
      if (query.agent_id) items = items.filter((item) => item.agent_id === query.agent_id);
      if (query.status) items = items.filter((item) => item.status === query.status);
      if (query.execution_type) {
        items = items.filter((item) => item.execution_type === query.execution_type);
      }

      const page = query.page ?? 1;
      const size = query.size ?? 20;
      const start = (page - 1) * size;

      return delay(
        wrap({
          items: items.slice(start, start + size),
          total: items.length,
          page,
          size,
        }),
      );
    }

    return http.get<PagedResponse<ToolExecutionRecord>>("/v1/tools/executions", {
      params: query,
    }) as Promise<Wrapped<PagedResponse<ToolExecutionRecord>>>;
  },

  async getExecutionOverview(): Promise<Wrapped<ExecutionOverview>> {
    if (USE_MOCK) return delay(wrap(mockExecutionOverview()));
    return http.get<ExecutionOverview>("/v1/tools/executions/overview") as Promise<
      Wrapped<ExecutionOverview>
    >;
  },

  async syncBuiltin(): Promise<Wrapped<ToolSyncResult>> {
    if (USE_MOCK) {
      return delay(
        wrap({
          created: 4,
          updated: 0,
          unchanged: 0,
          details: mockTools.slice(0, 4).map((tool) => ({
            tool_key: tool.tool_key,
            action: "created" as const,
          })),
        }),
        500,
      );
    }

    return http.post<ToolSyncResult>("/v1/tools/sync/builtin") as Promise<Wrapped<ToolSyncResult>>;
  },

  async listVersions(toolId: string): Promise<Wrapped<ToolVersion[]>> {
    return http.get<ToolVersion[]>(`/v1/tools/${toolId}/versions`) as Promise<Wrapped<ToolVersion[]>>;
  },

  async createVersion(
    toolId: string,
    payload: ToolVersionCreateRequest,
  ): Promise<Wrapped<ToolVersion>> {
    return http.post<ToolVersion>(`/v1/tools/${toolId}/versions`, payload) as Promise<Wrapped<ToolVersion>>;
  },

  async publishVersion(toolId: string, versionId: string): Promise<Wrapped<{ success: boolean }>> {
    return http.post<{ success: boolean }>(
      `/v1/tools/${toolId}/versions/${versionId}/publish`,
    ) as Promise<Wrapped<{ success: boolean }>>;
  },

  async rollbackVersion(toolId: string, versionId: string): Promise<Wrapped<{ success: boolean }>> {
    return http.post<{ success: boolean }>(
      `/v1/tools/${toolId}/versions/${versionId}/rollback`,
    ) as Promise<Wrapped<{ success: boolean }>>;
  },

  async listBindings(toolId?: string): Promise<Wrapped<AgentToolBinding[]>> {
    return http.get<AgentToolBinding[]>("/v1/tools/bindings", {
      params: toolId ? { tool_id: toolId } : {},
    }) as Promise<Wrapped<AgentToolBinding[]>>;
  },

  async createBinding(payload: BindingCreateRequest): Promise<Wrapped<AgentToolBinding>> {
    return http.post<AgentToolBinding>("/v1/tools/bindings", payload) as Promise<
      Wrapped<AgentToolBinding>
    >;
  },

  async updateBinding(id: string, payload: BindingUpdateRequest): Promise<Wrapped<AgentToolBinding>> {
    return http.put<AgentToolBinding>(`/v1/tools/bindings/${id}`, payload) as Promise<
      Wrapped<AgentToolBinding>
    >;
  },

  async deleteBinding(id: string): Promise<Wrapped<{ deleted: boolean }>> {
    return http.delete<{ deleted: boolean }>(`/v1/tools/bindings/${id}`) as Promise<
      Wrapped<{ deleted: boolean }>
    >;
  },
};
