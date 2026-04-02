export const opsRoutes = [
  {
    path: "runtime",
    name: "ops-runtime",
    component: () => import("@/views/OpsRuntimeView.vue"),
    meta: { title: "Agent 运行中心" },
  },
  {
    path: "rag-analysis",
    name: "ops-rag-analysis",
    component: () => import("@/views/ops/RagAnalysisView.vue"),
    meta: { title: "RAG 召回分析", roles: ["admin", "agent_operator"] },
  },
  {
    path: "analytics",
    name: "ops-analytics",
    component: () => import("@/views/AnalyticsView.vue"),
    meta: { title: "分析中心", roles: ["admin", "agent_operator"] },
  },
  {
    path: "analytics/report",
    name: "ops-analytics-report",
    redirect: "/ops/analytics?tab=quality",
  },
  {
    path: "analytics/tracing",
    name: "ops-analytics-tracing",
    redirect: "/ops/analytics?tab=tracing",
  },
  {
    path: "billing",
    name: "ops-billing",
    component: () => import("@/views/admin/TokenBillingView.vue"),
    meta: { title: "Token 成本", roles: ["admin", "agent_operator"] },
  },
  {
    path: "gpu",
    name: "ops-gpu",
    component: () => import("@/views/admin/GpuMonitorView.vue"),
    meta: { title: "GPU 监控", roles: ["admin", "agent_operator"] },
  },
];
