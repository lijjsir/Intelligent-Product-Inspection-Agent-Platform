import { ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER, ROLE_PLATFORM_OPERATOR } from "@/constants/roles";

export const governanceRoutes = [
  // Admin section
  { path: "admin/users", name: "governance-admin-users", component: () => import("@/views/UserListView.vue"), meta: { title: "用户管理", roles: [ROLE_ADMIN] } },
  { path: "admin/roles-orgs", name: "governance-admin-roles-orgs", component: () => import("@/views/admin/RolesOrgsView.vue"), meta: { title: "权限与组织", roles: [ROLE_ADMIN] } },
  { path: "admin/models", name: "governance-admin-models", component: () => import("@/views/admin/ModelConfigView.vue"), meta: { title: "模型配置", roles: [ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER] } },
  { path: "admin/infrastructure", name: "governance-admin-infrastructure", component: () => import("@/views/admin/InfrastructureView.vue"), meta: { title: "存储/基础设施", roles: [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR] } },
  { path: "admin/gpu", name: "governance-admin-gpu", component: () => import("@/views/admin/GpuMonitorView.vue"), meta: { title: "GPU 调度", roles: [ROLE_ADMIN, ROLE_ALGORITHM_ENGINEER] } },
  { path: "admin/inspection-standards", name: "governance-admin-inspection-standards", component: () => import("@/views/admin/InspectionStandardLibraryView.vue"), meta: { title: "检测标准", roles: [ROLE_ADMIN] } },
  { path: "admin/inspection-specs", name: "governance-admin-inspection-specs", component: () => import("@/views/admin/InspectionSpecView.vue"), meta: { title: "质检门槛", roles: [ROLE_ADMIN] } },
  { path: "admin/logs", name: "governance-admin-logs", component: () => import("@/views/admin/LogCenterView.vue"), meta: { title: "日志中心", roles: [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR] } },
  { path: "admin/approvals", name: "governance-admin-approvals", component: () => import("@/views/admin/ApprovalView.vue"), meta: { title: "高风险审批", roles: [ROLE_ADMIN] } },
  { path: "admin/meetings", name: "governance-admin-meetings", component: () => import("@/views/admin/MeetingManageView.vue"), meta: { title: "会议管理", roles: [ROLE_ADMIN] } },

  // Quality section
  { path: "quality/analysis-center", name: "governance-analysis-center", component: () => import("@/views/quality/AnalysisCenterView.vue"), meta: { title: "分析中心", roles: [ROLE_ADMIN] } },
  { path: "quality/report", name: "governance-quality-report", redirect: { name: "governance-analysis-center", query: { tab: "quality" } }, meta: { title: "质量报告", roles: [ROLE_ADMIN] } },
  { path: "quality/tracing", name: "governance-quality-tracing", redirect: { name: "governance-analysis-center", query: { tab: "tracing" } }, meta: { title: "质量追踪", roles: [ROLE_ADMIN] } },

  // Memory governance
  { path: "memory", name: "governance-memory", component: () => import("@/views/admin/MemoryGovernanceView.vue"), meta: { title: "记忆治理", roles: [ROLE_ADMIN, ROLE_PLATFORM_OPERATOR] } },
];
