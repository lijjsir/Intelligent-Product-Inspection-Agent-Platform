import { ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER } from "@/constants/roles";

export const governanceRoutes = [
  ...["enterprises", "devices"].map((kind) => ({
    path: `admin/${kind}`,
    name: `governance-admin-${kind}`,
    component: () => import("@/views/supervision/SupervisionRecordsView.vue"),
    meta: {
      title: (
        { enterprises: "监管对象", devices: "设备资源" } as Record<
          string,
          string
        >
      )[kind],
      supervisionKind: kind,
      roles: [ROLE_ADMIN],
    },
  })),
  // Admin section
  {
    path: "admin/users",
    name: "governance-admin-users",
    component: () => import("@/views/UserListView.vue"),
    meta: { title: "用户管理", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/roles-orgs",
    name: "governance-admin-roles-orgs",
    component: () => import("@/views/admin/RolesOrgsView.vue"),
    meta: { title: "权限与组织", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/models",
    name: "governance-admin-models",
    component: () => import("@/views/admin/ModelConfigView.vue"),
    meta: { title: "模型配置", roles: [ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "admin/infrastructure",
    name: "governance-admin-infrastructure",
    component: () => import("@/views/admin/InfrastructureView.vue"),
    meta: { title: "存储/基础设施", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/gpu",
    name: "governance-admin-gpu",
    component: () => import("@/views/admin/GpuMonitorView.vue"),
    meta: { title: "GPU 调度", roles: [ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "admin/product-master",
    name: "governance-admin-product-master",
    redirect: { name: "governance-admin-quality-products" },
    meta: { title: "产品类别与产品", roles: [ROLE_ADMIN], hiddenInMenu: true },
  },
  {
    path: "admin/quality-products",
    name: "governance-admin-quality-products",
    component: () => import("@/views/admin/QualityProductView.vue"),
    meta: { title: "产品类别与产品", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/quality-data-sources",
    name: "governance-admin-quality-data-sources",
    component: () => import("@/views/admin/QualityDataSourceView.vue"),
    meta: { title: "数据来源", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/inspection-standards",
    name: "governance-admin-inspection-standards",
    component: () => import("@/views/admin/InspectionStandardLibraryView.vue"),
    meta: { title: "检测标准", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/inspection-specs",
    name: "governance-admin-inspection-specs",
    component: () => import("@/views/admin/StandardExecutionRuleView.vue"),
    meta: { title: "标准条款判定条件", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/ai-review-gates",
    name: "governance-admin-ai-review-gates",
    component: () => import("@/views/admin/InspectionSpecView.vue"),
    meta: { title: "质检门槛", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/risk-policies",
    name: "governance-admin-risk-policies",
    component: () => import("@/views/admin/RiskPolicyView.vue"),
    meta: { title: "风险等级规则", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/alert-rules",
    name: "governance-admin-alert-rules",
    component: () => import("@/views/ops/AlertRuleView.vue"),
    meta: { title: "告警规则", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/logs",
    name: "governance-admin-logs",
    component: () => import("@/views/admin/LogCenterView.vue"),
    meta: { title: "日志中心", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/approvals",
    name: "governance-admin-approvals",
    component: () => import("@/views/admin/ApprovalView.vue"),
    meta: { title: "高风险审批", roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/meetings",
    name: "governance-admin-meetings",
    component: () => import("@/views/admin/MeetingManageView.vue"),
    meta: { title: "会议管理", roles: [ROLE_ADMIN] },
  },

  // Quality section
  {
    path: "quality/analysis-center",
    name: "governance-analysis-center",
    component: () => import("@/views/quality/AnalysisCenterView.vue"),
    meta: { title: "分析中心", roles: [ROLE_ADMIN] },
  },
  {
    path: "quality/report",
    name: "governance-quality-report",
    redirect: { name: "governance-analysis-center", query: { tab: "quality" } },
    meta: { title: "质量报告", roles: [ROLE_ADMIN] },
  },
  {
    path: "quality/tracing",
    name: "governance-quality-tracing",
    redirect: { name: "governance-analysis-center", query: { tab: "tracing" } },
    meta: { title: "质量追踪", roles: [ROLE_ADMIN] },
  },

  // Memory governance
  {
    path: "memory",
    name: "governance-memory",
    component: () => import("@/views/admin/MemoryGovernanceView.vue"),
    meta: { title: "记忆治理", roles: [ROLE_ADMIN] },
  },
];
