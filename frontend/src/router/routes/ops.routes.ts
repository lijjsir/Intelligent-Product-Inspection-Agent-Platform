export const opsRoutes = [
  { path: "runtime", name: "ops-runtime", component: () => import("@/views/OpsRuntimeView.vue") },
  {
    path: "agents",
    name: "ops-agents",
    component: () => import("@/views/ops/AgentManageView.vue"),
    meta: { title: "Agent 管理", roles: ["admin", "agent_operator"] },
  },
  {
    path: "prompts",
    name: "ops-prompts",
    component: () => import("@/views/ops/PromptManageView.vue"),
    meta: { title: "Prompt 管理", roles: ["admin", "agent_operator"] },
  },
  {
    path: "intent-routes",
    name: "ops-intent-routes",
    component: () => import("@/views/ops/IntentRouteView.vue"),
    meta: { title: "意图路由配置", roles: ["admin", "agent_operator"] },
  },
  {
    path: "rag-analysis",
    name: "ops-rag-analysis",
    component: () => import("@/views/ops/RagAnalysisView.vue"),
    meta: { title: "RAG 召回分析", roles: ["admin", "agent_operator"] },
  },
];
