import {
  ROLE_ADMIN,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_APP_DEVELOPER,
  ROLE_EXPERT,
  ROLE_PLATFORM_OPERATOR,
  ROLE_USER,
} from "@/constants/roles";

const Placeholder = () => import("@/views/placeholder/PlaceholderPage.vue");

const SHARED_AGENT_OPS_ROLES = [
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_PLATFORM_OPERATOR,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_EXPERT,
  ROLE_USER,
];

const TOOL_MANAGEMENT_ROLES = [ROLE_ADMIN, ROLE_APP_DEVELOPER];

export const opsRoutes = [
  {
    path: "tools",
    name: "ops-tools-overview",
    component: () => import("@/views/ops/tools/ToolOverviewView.vue"),
    meta: { title: "工具总览", roles: TOOL_MANAGEMENT_ROLES },
  },
  {
    path: "tools/catalog",
    name: "ops-tools-catalog",
    component: () => import("@/views/ops/tools/ToolCatalogView.vue"),
    meta: { title: "工具库", roles: TOOL_MANAGEMENT_ROLES },
  },
  {
    path: "tools/catalog/:id",
    name: "ops-tools-detail",
    component: () => import("@/views/ops/tools/ToolDetailView.vue"),
    meta: { title: "工具详情", hiddenInMenu: true, roles: TOOL_MANAGEMENT_ROLES },
  },
  {
    path: "tools/import",
    name: "ops-tools-import",
    component: () => import("@/views/ops/tools/ToolImportView.vue"),
    meta: { title: "外部导入", roles: TOOL_MANAGEMENT_ROLES },
  },
  {
    path: "tools/bindings",
    name: "ops-tools-bindings",
    component: () => import("@/views/ops/tools/ToolBindingView.vue"),
    meta: { title: "Agent 绑定", roles: TOOL_MANAGEMENT_ROLES },
  },
  {
    path: "tools/executions",
    name: "ops-tools-executions",
    component: () => import("@/views/ops/tools/ToolExecutionView.vue"),
    meta: { title: "执行监控", roles: TOOL_MANAGEMENT_ROLES },
  },

  {
    path: "agents",
    name: "ops-agents",
    component: () => import("@/views/ops/AgentManageView.vue"),
    meta: { title: "Agent 管理", roles: SHARED_AGENT_OPS_ROLES },
  },
  {
    path: "agents/intent-routes",
    name: "ops-agents-intent-routes",
    component: () => import("@/views/ops/IntentRouteView.vue"),
    meta: { title: "路由策略", roles: SHARED_AGENT_OPS_ROLES },
  },
  {
    path: "prompts",
    name: "ops-prompts",
    component: () => import("@/views/ops/PromptManageView.vue"),
    meta: { title: "Prompt 管理", roles: SHARED_AGENT_OPS_ROLES },
  },
  {
    path: "rag",
    name: "ops-rag",
    component: () => import("@/views/ops/RagAnalysisView.vue"),
    meta: { title: "RAG 分析", roles: SHARED_AGENT_OPS_ROLES },
  },

  {
    path: "analytics",
    name: "ops-analytics",
    component: () => import("@/views/AnalyticsView.vue"),
    meta: { title: "分析看板", roles: [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "analytics/behavior",
    name: "ops-analytics-behavior",
    component: Placeholder,
    meta: { title: "用户行为分析", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "analytics/reports",
    name: "ops-analytics-reports",
    component: Placeholder,
    meta: { title: "业务报表", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "analytics/cost",
    name: "ops-analytics-cost",
    component: Placeholder,
    meta: { title: "成本分析", roles: [ROLE_PLATFORM_OPERATOR] },
  },

  {
    path: "billing",
    name: "ops-billing",
    component: () => import("@/views/admin/TokenBillingView.vue"),
    meta: { title: "计费管理", roles: [ROLE_ADMIN] },
  },

  {
    path: "templates/review",
    name: "ops-templates-review",
    component: Placeholder,
    meta: { title: "模板审核", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "models/versions",
    name: "ops-models-versions",
    component: Placeholder,
    meta: { title: "模型版本", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "models/monitor",
    name: "ops-models-monitor",
    component: Placeholder,
    meta: { title: "调用监控", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "data-quality",
    name: "ops-data-quality",
    component: Placeholder,
    meta: { title: "数据质量", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "label-tasks",
    name: "ops-label-tasks",
    component: Placeholder,
    meta: { title: "标注任务", roles: [ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "data-review",
    name: "ops-data-review",
    component: Placeholder,
    meta: { title: "数据审核", roles: [ROLE_PLATFORM_OPERATOR] },
  },

  {
    path: "data/import",
    name: "ops-data-import",
    component: Placeholder,
    meta: { title: "数据接入", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "data/processing",
    name: "ops-data-processing",
    component: Placeholder,
    meta: { title: "数据处理", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "data/eval-sets",
    name: "ops-data-eval-sets",
    component: Placeholder,
    meta: { title: "测试集管理", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "training/jobs",
    name: "ops-training-jobs",
    component: Placeholder,
    meta: { title: "训练任务", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "training/fine-tune",
    name: "ops-training-fine-tune",
    component: Placeholder,
    meta: { title: "微调管理", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "eval/offline",
    name: "ops-eval-offline",
    component: Placeholder,
    meta: { title: "离线评测", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "eval/online",
    name: "ops-eval-online",
    component: Placeholder,
    meta: { title: "在线验证", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "experiments",
    name: "ops-experiments",
    component: Placeholder,
    meta: { title: "实验追踪", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "deployments",
    name: "ops-deployments",
    component: Placeholder,
    meta: { title: "部署记录", roles: [ROLE_ALGORITHM_ENGINEER] },
  },
];
