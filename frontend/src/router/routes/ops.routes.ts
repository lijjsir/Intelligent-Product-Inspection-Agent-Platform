import { ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER } from "@/constants/roles";

const Placeholder = () => import("@/views/placeholder/PlaceholderPage.vue");

export const opsRoutes = [
  // Agents section
  { path: "agents", name: "ops-agents", component: () => import("@/views/ops/AgentManageView.vue"), meta: { title: "Agent 管理", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR] } },
  { path: "agents/topology", name: "ops-agents-topology", component: Placeholder, meta: { title: "Agent 拓扑图", roles: [ROLE_APP_DEVELOPER] } },
  { path: "agents/intent-routes", name: "ops-agents-intent-routes", component: () => import("@/views/ops/IntentRouteView.vue"), meta: { title: "路由策略", roles: [ROLE_APP_DEVELOPER] } },

  // Prompts section
  { path: "prompts", name: "ops-prompts", component: () => import("@/views/ops/PromptManageView.vue"), meta: { title: "Prompt 管理", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] } },
  { path: "prompts/dspy", name: "ops-prompts-dspy", component: Placeholder, meta: { title: "DSPy 优化", roles: [ROLE_APP_DEVELOPER] } },

  // RAG section
  { path: "rag", name: "ops-rag", component: () => import("@/views/ops/RagAnalysisView.vue"), meta: { title: "RAG 配置", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] } },
  { path: "rag/policies", name: "ops-rag-policies", component: Placeholder, meta: { title: "召回策略", roles: [ROLE_APP_DEVELOPER] } },

  // Developer tools
  { path: "workflows", name: "ops-workflows", component: Placeholder, meta: { title: "流程节点", roles: [ROLE_APP_DEVELOPER] } },
  { path: "tools", name: "ops-tools-overview", component: () => import("@/views/ops/tools/ToolOverviewView.vue"), meta: { title: "工具总览", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] } },
  { path: "tools/catalog", name: "ops-tools-catalog", component: () => import("@/views/ops/tools/ToolCatalogView.vue"), meta: { title: "工具库", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] } },
  { path: "tools/catalog/:id", name: "ops-tools-detail", component: () => import("@/views/ops/tools/ToolDetailView.vue"), meta: { title: "工具详情", hiddenInMenu: true, roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] } },
  { path: "tools/import", name: "ops-tools-import", component: () => import("@/views/ops/tools/ToolImportView.vue"), meta: { title: "外部导入", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] } },
  { path: "tools/bindings", name: "ops-tools-bindings", component: () => import("@/views/ops/tools/ToolBindingView.vue"), meta: { title: "Agent 绑定", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] } },
  { path: "tools/executions", name: "ops-tools-executions", component: () => import("@/views/ops/tools/ToolExecutionView.vue"), meta: { title: "执行监控", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER] } },

  // Releases
  { path: "releases", name: "ops-releases", component: Placeholder, meta: { title: "发布管理", roles: [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR] } },

  // Analytics
  { path: "analytics", name: "ops-analytics", component: () => import("@/views/AnalyticsView.vue"), meta: { title: "分析看板", roles: [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR] } },
  { path: "analytics/behavior", name: "ops-analytics-behavior", component: Placeholder, meta: { title: "用户行为分析", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "analytics/reports", name: "ops-analytics-reports", component: Placeholder, meta: { title: "业务报表", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "analytics/cost", name: "ops-analytics-cost", component: Placeholder, meta: { title: "成本分析", roles: [ROLE_PLATFORM_OPERATOR] } },

  // Billing
  { path: "billing", name: "ops-billing", component: () => import("@/views/admin/TokenBillingView.vue"), meta: { title: "计费管理", roles: [ROLE_ADMIN] } },

  // Platform operator section
  { path: "templates/review", name: "ops-templates-review", component: Placeholder, meta: { title: "模板审核", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "models/versions", name: "ops-models-versions", component: Placeholder, meta: { title: "模型版本", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "models/monitor", name: "ops-models-monitor", component: Placeholder, meta: { title: "调用监控", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "data-quality", name: "ops-data-quality", component: Placeholder, meta: { title: "数据质量", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "label-tasks", name: "ops-label-tasks", component: Placeholder, meta: { title: "标注任务", roles: [ROLE_PLATFORM_OPERATOR] } },
  { path: "data-review", name: "ops-data-review", component: Placeholder, meta: { title: "数据审核", roles: [ROLE_PLATFORM_OPERATOR] } },

  // Algorithm engineer section
  { path: "data/import", name: "ops-data-import", component: () => import("@/views/ops/DatasetImportListView.vue"), meta: { title: "数据接入", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "data/import/:id", name: "ops-data-import-detail", component: () => import("@/views/ops/DatasetImportDetailView.vue"), meta: { title: "数据集详情", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "data/processing", name: "ops-data-processing", component: () => import("@/views/ops/DataProcessingView.vue"), meta: { title: "数据处理", roles: [ROLE_ALGORITHM_ENGINEER], hidden: true } },
  { path: "data/eval-sets", name: "ops-data-eval-sets", component: () => import("@/views/ops/EvalDatasetListView.vue"), meta: { title: "测试集管理", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "data/eval-sets/:id", name: "ops-data-eval-sets-detail", component: () => import("@/views/ops/EvalDatasetDetailView.vue"), meta: { title: "评测集详情", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "training/jobs", name: "ops-training-jobs", component: () => import("@/views/ops/TrainingJobsView.vue"), meta: { title: "训练任务", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "training/jobs/:id", name: "ops-training-jobs-detail", component: () => import("@/views/ops/TrainingJobDetailView.vue"), meta: { title: "训练任务详情", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "training/fine-tune", name: "ops-training-fine-tune", component: () => import("@/views/ops/FineTuneManageView.vue"), meta: { title: "微调管理", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "training/fine-tune/:id", name: "ops-training-fine-tune-detail", component: () => import("@/views/ops/FineTuneDetailView.vue"), meta: { title: "微调详情", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "eval/offline", name: "ops-eval-offline", component: () => import("@/views/ops/OfflineEvaluationView.vue"), meta: { title: "离线评测", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "eval/offline/:id", name: "ops-eval-offline-detail", component: () => import("@/views/ops/OfflineEvaluationDetailView.vue"), meta: { title: "离线评测详情", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "eval/online", name: "ops-eval-online", component: () => import("@/views/ops/OnlineValidationView.vue"), meta: { title: "在线验证", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "eval/online/:id", name: "ops-eval-online-detail", component: () => import("@/views/ops/OnlineValidationDetailView.vue"), meta: { title: "在线验证详情", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "experiments", name: "ops-experiments", component: () => import("@/views/ops/ExperimentTrackingView.vue"), meta: { title: "实验追踪", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "experiments/:id", name: "ops-experiments-detail", component: () => import("@/views/ops/ExperimentDetailView.vue"), meta: { title: "实验详情", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "deployments", name: "ops-deployments", component: () => import("@/views/ops/DeploymentRecordsView.vue"), meta: { title: "部署记录", roles: [ROLE_ALGORITHM_ENGINEER] } },
  { path: "deployments/:id", name: "ops-deployments-detail", component: () => import("@/views/ops/DeploymentDetailView.vue"), meta: { title: "部署详情", roles: [ROLE_ALGORITHM_ENGINEER] } },
];
