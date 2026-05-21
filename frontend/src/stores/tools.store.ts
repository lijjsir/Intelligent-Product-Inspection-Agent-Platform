import { defineStore } from "pinia";
import { ref } from "vue";
import { toolsApi } from "@/api/tools.api";
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


export const useToolsStore = defineStore("tools", () => {
  const overview = ref<ToolOverview | null>(null);
  const overviewLoading = ref(false);

  const tools = ref<ToolDefinition[]>([]);
  const toolsTotal = ref(0);
  const toolsLoading = ref(false);

  const currentTool = ref<ToolDetail | null>(null);
  const currentToolLoading = ref(false);

  const executions = ref<ToolExecutionRecord[]>([]);
  const executionsTotal = ref(0);
  const executionsLoading = ref(false);
  const executionOverview = ref<ExecutionOverview | null>(null);

  const testResult = ref<ToolTestResult | null>(null);
  const testRunning = ref(false);

  const syncingBuiltin = ref(false);
  const lastSyncResult = ref<ToolSyncResult | null>(null);

  const toolVersions = ref<ToolVersion[]>([]);
  const toolBindings = ref<AgentToolBinding[]>([]);

  async function fetchOverview() {
    overviewLoading.value = true;
    try {
      const { data } = await toolsApi.getOverview();
      overview.value = data.data;
    } finally {
      overviewLoading.value = false;
    }
  }

  async function fetchTools(query: ToolListQuery = {}) {
    toolsLoading.value = true;
    try {
      const { data } = await toolsApi.listTools(query);
      tools.value = data.data.items;
      toolsTotal.value = data.data.total;
    } finally {
      toolsLoading.value = false;
    }
  }

  async function fetchToolDetail(id: string) {
    currentToolLoading.value = true;
    try {
      const { data } = await toolsApi.getTool(id);
      currentTool.value = data.data;
    } finally {
      currentToolLoading.value = false;
    }
  }

  async function createTool(payload: ToolCreateRequest) {
    const { data } = await toolsApi.createTool(payload);
    return data.data;
  }

  async function updateTool(id: string, payload: ToolUpdateRequest) {
    const { data } = await toolsApi.updateTool(id, payload);
    if (currentTool.value?.id === id) {
      currentTool.value = { ...currentTool.value, ...data.data };
    }
    tools.value = tools.value.map((tool) => (tool.id === id ? { ...tool, ...data.data } : tool));
    return data.data;
  }

  async function updateToolStatus(id: string, status: string) {
    const { data } = await toolsApi.updateToolStatus(id, status);
    if (currentTool.value?.id === id) {
      currentTool.value.status = data.data.status;
    }
    tools.value = tools.value.map((tool) =>
      tool.id === id ? { ...tool, status: data.data.status } : tool
    );
    return data.data;
  }

  async function testTool(toolId: string, params: Record<string, unknown>) {
    testRunning.value = true;
    testResult.value = null;
    try {
      const { data } = await toolsApi.testTool(toolId, params);
      testResult.value = data.data;
      return data.data;
    } finally {
      testRunning.value = false;
    }
  }

  async function fetchExecutions(query: ExecutionListQuery = {}) {
    executionsLoading.value = true;
    try {
      const { data } = await toolsApi.listExecutions(query);
      executions.value = data.data.items;
      executionsTotal.value = data.data.total;
    } finally {
      executionsLoading.value = false;
    }
  }

  async function fetchExecutionOverview() {
    const { data } = await toolsApi.getExecutionOverview();
    executionOverview.value = data.data;
  }

  async function syncBuiltin() {
    syncingBuiltin.value = true;
    try {
      const { data } = await toolsApi.syncBuiltin();
      lastSyncResult.value = data.data;
      return data.data;
    } finally {
      syncingBuiltin.value = false;
    }
  }

  async function fetchVersions(toolId: string) {
    const { data } = await toolsApi.listVersions(toolId);
    toolVersions.value = data.data;
    return data.data;
  }

  async function createVersion(toolId: string, payload: ToolVersionCreateRequest) {
    const { data } = await toolsApi.createVersion(toolId, payload);
    toolVersions.value.unshift(data.data);
    return data.data;
  }

  async function publishVersion(toolId: string, versionId: string) {
    const { data } = await toolsApi.publishVersion(toolId, versionId);
    return data.data;
  }

  async function rollbackVersion(toolId: string, versionId: string) {
    const { data } = await toolsApi.rollbackVersion(toolId, versionId);
    return data.data;
  }

  async function fetchBindings(toolId?: string) {
    const { data } = await toolsApi.listBindings(toolId);
    toolBindings.value = data.data;
    return data.data;
  }

  async function createBinding(payload: BindingCreateRequest) {
    const { data } = await toolsApi.createBinding(payload);
    toolBindings.value.push(data.data);
    return data.data;
  }

  async function updateBinding(id: string, payload: BindingUpdateRequest) {
    const { data } = await toolsApi.updateBinding(id, payload);
    toolBindings.value = toolBindings.value.map((b) =>
      b.id === id ? { ...b, ...data.data } : b
    );
    return data.data;
  }

  async function deleteBinding(id: string) {
    const { data } = await toolsApi.deleteBinding(id);
    toolBindings.value = toolBindings.value.filter((b) => b.id !== id);
    return data.data;
  }

  function $reset() {
    overview.value = null;
    tools.value = [];
    toolsTotal.value = 0;
    currentTool.value = null;
    executions.value = [];
    executionsTotal.value = 0;
    executionOverview.value = null;
    testResult.value = null;
    lastSyncResult.value = null;
    toolVersions.value = [];
    toolBindings.value = [];
  }

  return {
    overview,
    overviewLoading,
    tools,
    toolsTotal,
    toolsLoading,
    currentTool,
    currentToolLoading,
    executions,
    executionsTotal,
    executionsLoading,
    executionOverview,
    testResult,
    testRunning,
    syncingBuiltin,
    lastSyncResult,
    fetchOverview,
    fetchTools,
    fetchToolDetail,
    createTool,
    updateTool,
    updateToolStatus,
    testTool,
    fetchExecutions,
    fetchExecutionOverview,
    syncBuiltin,
    toolVersions,
    toolBindings,
    fetchVersions,
    createVersion,
    publishVersion,
    rollbackVersion,
    fetchBindings,
    createBinding,
    updateBinding,
    deleteBinding,
    $reset,
  };
});
