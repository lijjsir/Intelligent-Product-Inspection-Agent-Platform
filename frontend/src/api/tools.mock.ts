import type {
  ExecutionOverview,
  ToolDefinition,
  ToolDetail,
  ToolExecutionRecord,
  ToolOverview,
  ToolTestResult,
  TrendPoint,
} from "@/types/tools.types";


const now = Date.now();

function ts(minutesAgo = 0): string {
  return new Date(now - minutesAgo * 60_000).toISOString();
}

function trend(center: number, count: number, variance: number): TrendPoint[] {
  return Array.from({ length: count }, (_, index) => ({
    time: ts((count - index) * 5),
    value: Math.max(0, Math.round(center + (Math.random() - 0.5) * variance)),
  }));
}

export const mockTools: ToolDefinition[] = [
  {
    id: "tool-rag-standard",
    tool_key: "rag.standard_search",
    display_name: "标准知识库检索",
    description: "从标准知识空间检索条款和证据片段。",
    category: "RAG",
    tool_type: "rag",
    status: "active",
    risk_level: "low",
    is_readonly: true,
    source_type: "builtin",
    health_status: "healthy",
    active_version: "1.0.0",
    bound_agent_names: ["Chat Agent", "Task Inspection Agent"],
    today_calls: 128,
    success_rate: 0.982,
    avg_latency_ms: 320,
    created_at: ts(24 * 60),
    updated_at: ts(30),
  },
  {
    id: "tool-file-parse",
    tool_key: "file.parse",
    display_name: "文件内容解析",
    description: "解析 PDF、Word、Excel、CSV 和 JSON 文件内容。",
    category: "file_parse",
    tool_type: "native",
    status: "active",
    risk_level: "low",
    is_readonly: true,
    source_type: "builtin",
    health_status: "healthy",
    active_version: "1.0.0",
    bound_agent_names: ["Task Inspection Agent", "Report Generator"],
    today_calls: 86,
    success_rate: 0.964,
    avg_latency_ms: 210,
    created_at: ts(48 * 60),
    updated_at: ts(60),
  },
  {
    id: "tool-score",
    tool_key: "calc.inspection_score",
    display_name: "检测评分计算",
    description: "根据证据数量和检测规则生成评分结果。",
    category: "inspection_calc",
    tool_type: "native",
    status: "active",
    risk_level: "medium",
    is_readonly: false,
    source_type: "builtin",
    health_status: "degraded",
    active_version: "1.0.0",
    bound_agent_names: ["Task Inspection Agent"],
    today_calls: 52,
    success_rate: 0.91,
    avg_latency_ms: 155,
    created_at: ts(72 * 60),
    updated_at: ts(90),
  },
];

export function mockToolOverview(): ToolOverview {
  return {
    total_tools: mockTools.length,
    active_tools: mockTools.filter((tool) => tool.status === "active").length,
    error_tools: mockTools.filter((tool) => tool.health_status !== "healthy").length,
    today_calls: mockTools.reduce((sum, tool) => sum + tool.today_calls, 0),
    avg_latency_ms: 228,
    high_risk_tools: mockTools.filter((tool) => tool.risk_level === "high").length,
    call_trend: trend(60, 24, 24),
    health_distribution: {
      healthy: 2,
      degraded: 1,
      unhealthy: 0,
      unknown: 0,
    },
    error_trend: trend(2, 24, 3),
    top_failing: [
      {
        tool_id: "tool-score",
        tool_name: "检测评分计算",
        failure_count: 5,
        failure_rate: 0.09,
      },
    ],
    high_latency: [
      {
        tool_id: "tool-rag-standard",
        tool_name: "标准知识库检索",
        avg_latency_ms: 320,
      },
    ],
    pending_risk_tools: [],
    critical_dependencies: [
      {
        tool_id: "tool-rag-standard",
        tool_name: "标准知识库检索",
        dependent_agents: 2,
      },
    ],
  };
}

export const mockExecutions: ToolExecutionRecord[] = Array.from({ length: 20 }, (_, index) => ({
  id: `exec-${index + 1}`,
  tool_id: mockTools[index % mockTools.length].id,
  tool_name: mockTools[index % mockTools.length].display_name,
  agent_id: `agent-${(index % 3) + 1}`,
  agent_name: ["Chat Agent", "Task Inspection Agent", "Report Generator"][index % 3],
  task_id: `task-${100 + index}`,
  execution_type: index % 5 === 0 ? "test" : "runtime",
  status: index % 6 === 0 ? "failed" : "success",
  duration_ms: 120 + index * 13,
  input_summary: JSON.stringify({ query: `mock-query-${index}` }),
  output_summary: JSON.stringify({ total: (index % 4) + 1 }),
  error_message: index % 6 === 0 ? "mock timeout" : undefined,
  trace_id: `trace-${index + 1}`,
  created_at: ts(index * 8),
}));

export function mockExecutionOverview(): ExecutionOverview {
  return {
    today_calls: mockExecutions.length,
    success_rate: 0.9,
    avg_latency_ms: 240,
    failed_count: mockExecutions.filter((item) => item.status !== "success").length,
    call_trend: trend(12, 60, 10),
    error_trend: trend(1, 60, 2),
    latency_trend: trend(240, 60, 90),
  };
}

export function mockToolDetail(id: string): ToolDetail {
  const tool = mockTools.find((item) => item.id === id) ?? mockTools[0];
  return {
    ...tool,
    active_version_id: `${tool.id}:1.0.0`,
    versions: [
      {
        id: `${tool.id}:1.0.0`,
        tool_id: tool.id,
        version: "1.0.0",
        display_name: tool.display_name,
        description: "当前生效版本",
        handler_path: tool.tool_type === "http" ? undefined : `agent.tools.builtin.${tool.tool_key.replace(/\./g, "_")}`,
        endpoint: tool.tool_type === "http" ? "https://example.com/api/tools" : undefined,
        method: tool.tool_type === "http" ? "POST" : undefined,
        parameters_schema: {
          type: "object",
          properties: {
            query: { type: "string" },
          },
          required: ["query"],
        },
        returns_schema: {
          type: "object",
          properties: {
            total: { type: "integer" },
          },
        },
        auth_type: "none",
        timeout_ms: 30000,
        rate_limit_rpm: 60,
        status: "active",
        created_by: "system",
        created_at: ts(24 * 60),
        updated_at: ts(60),
      },
    ],
    executions: mockExecutions.filter((item) => item.tool_id === tool.id),
    bindings: [],
    endpoint: tool.tool_type === "http" ? "https://example.com/api/tools" : undefined,
    method: tool.tool_type === "http" ? "POST" : undefined,
    handler_path:
      tool.tool_type === "http" ? undefined : `agent.tools.builtin.${tool.tool_key.replace(/\./g, "_")}`,
    parameters_schema: {
      type: "object",
      properties: {
        query: { type: "string", description: "查询内容" },
      },
      required: ["query"],
    },
    returns_schema: {
      type: "object",
      properties: {
        total: { type: "integer" },
      },
    },
    auth_type: "none",
    timeout_ms: 30000,
    retry_policy: { max_retries: 1 },
    rate_limit_rpm: 60,
    audit_logs: [],
  };
}

export function mockToolTest(): ToolTestResult {
  return {
    status: "success",
    duration_ms: 180,
    output: { total: 1, documents: [] },
    trace_id: `trace-test-${Date.now()}`,
  };
}
