import { ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER } from "@/constants/roles";

const Placeholder = () => import("@/views/placeholder/PlaceholderPage.vue");

export const opsRoutes = [
  // Dashboard
  { path: "dashboard", name: "ops-dashboard", component: () => import("@/views/ops/OpsDashboardView.vue"), meta: { title: "平台运维工作台", roles: [ROLE_PLATFORM_OPERATOR] } },

  // Analytics
  { path: "analytics", name: "ops-analytics", component: () => import("@/views/AnalyticsView.vue"), meta: { title: "分析中心", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "analytics/behavior", name: "ops-analytics-behavior", component: Placeholder, meta: { title: "用户行为分析", roles: [ROLE_PLATFORM_OPERATOR] } },

  // Alerts
  { path: "alerts", name: "ops-alerts", component: () => import("@/views/ops/AlertManageView.vue"), meta: { title: "告警管理", roles: [ROLE_PLATFORM_OPERATOR] } },


  // Call monitor
  { path: "calls", name: "ops-calls", component: () => import("@/views/ops/ModelMonitorView.vue"), meta: { title: "调用监控", roles: [ROLE_PLATFORM_OPERATOR] } },

  // Data quality
  { path: "data-quality", name: "ops-data-quality", component: () => import("@/views/ops/DataQualityView.vue"), meta: { title: "数据质量", roles: [ROLE_PLATFORM_OPERATOR] } },

  // Cost analysis
  { path: "cost", name: "ops-cost", component: () => import("@/views/ops/CostAnalysisView.vue"), meta: { title: "成本分析", roles: [ROLE_PLATFORM_OPERATOR] } },

  // Reports
  { path: "reports", name: "ops-reports", component: () => import("@/views/ops/BizReportView.vue"), meta: { title: "业务报表", roles: [ROLE_PLATFORM_OPERATOR] } },

  // Cross-domain readonly
  { path: "agents", name: "ops-agents", component: () => import("@/views/ops/AgentManageView.vue"), meta: { title: "Agent 查看", roles: [ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR] } },
  { path: "stability", name: "ops-stability", component: () => import("@/views/StabilityOverviewView.vue"), meta: { title: "稳定性查看", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "inspection-specs", name: "ops-inspection-specs", component: () => import("@/views/admin/InspectionSpecView.vue"), meta: { title: "检测标准查看", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "tasks", name: "ops-tasks", component: () => import("@/views/TaskListView.vue"), meta: { title: "任务查看", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "tasks/:id", name: "ops-task-detail", component: () => import("@/views/TaskDetailView.vue"), meta: { roles: [ROLE_PLATFORM_OPERATOR] } },

  // App developer section
  { path: "agents/topology", name: "ops-agents-topology", component: Placeholder, meta: { title: "Agent 拓扑图", roles: [ROLE_APP_DEVELOPER] } },
  { path: "agents/intent-routes", name: "ops-agents-intent-routes", component: () => import("@/views/ops/IntentRouteView.vue"), meta: { title: "路由策略", roles: [ROLE_APP_DEVELOPER] } },

  { path: "prompts", name: "ops-prompts", component: () => import("@/views/ops/PromptManageView.vue"), meta: { title: "Prompt 管理", roles: [ROLE_APP_DEVELOPER] } },
  { path: "prompts/dspy", name: "ops-prompts-dspy", component: Placeholder, meta: { title: "DSPy 优化", roles: [ROLE_APP_DEVELOPER] } },

  { path: "rag", name: "ops-rag", component: () => import("@/views/ops/RagAnalysisView.vue"), meta: { title: "RAG 配置", roles: [ROLE_APP_DEVELOPER] } },
  { path: "rag/policies", name: "ops-rag-policies", component: Placeholder, meta: { title: "召回策略", roles: [ROLE_APP_DEVELOPER] } },

  { path: "workflows", name: "ops-workflows", component: Placeholder, meta: { title: "流程节点", roles: [ROLE_APP_DEVELOPER] } },
  { path: "tools", name: "ops-tools", component: Placeholder, meta: { title: "工具注册", roles: [ROLE_APP_DEVELOPER] } },

  { path: "releases", name: "ops-releases", component: () => import("@/views/ops/ReleaseView.vue"), meta: { title: "发布协同", roles: [ROLE_APP_DEVELOPER] } },
  { path: "templates/review", name: "ops-templates-review", component: () => import("@/views/ops/TemplateReviewView.vue"), meta: { title: "模板审核", roles: [ROLE_PLATFORM_OPERATOR] } },

  // Billing
  { path: "billing", name: "ops-billing", component: () => import("@/views/admin/TokenBillingView.vue"), meta: { title: "计费管理", roles: [ROLE_ADMIN] } },

  // Model operations
  { path: "models/config", name: "ops-models-config", component: () => import("@/views/admin/ModelConfigView.vue"), meta: { title: "模型配置", roles: [ROLE_ALGORITHM_ENGINEER] } },

  // Algorithm engineer section
  { path: "data/import", name: "ops-data-import", component: Placeholder, meta: { title: "数据接入", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "data/processing", name: "ops-data-processing", component: Placeholder, meta: { title: "数据处理", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "data/eval-sets", name: "ops-data-eval-sets", component: Placeholder, meta: { title: "测试集管理", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "training/jobs", name: "ops-training-jobs", component: Placeholder, meta: { title: "训练任务", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "training/fine-tune", name: "ops-training-fine-tune", component: Placeholder, meta: { title: "微调管理", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "eval/offline", name: "ops-eval-offline", component: Placeholder, meta: { title: "离线评测", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "eval/online", name: "ops-eval-online", component: Placeholder, meta: { title: "在线验证", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "experiments", name: "ops-experiments", component: Placeholder, meta: { title: "实验追踪", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "deployments", name: "ops-deployments", component: Placeholder, meta: { title: "部署记录", roles: [ROLE_ALGORITHM_ENGINEER] } },
];
