import { ROLE_ADMIN } from "@/constants/roles";

export const governanceRoutes = [
  {
    path: "admin/models",
    name: "governance-admin-models",
    component: () => import("@/views/admin/ModelConfigView.vue"),
    meta: { roles: [ROLE_ADMIN] },
  },
  {
    path: "data-management",
    name: "governance-data-management",
    component: () => import("@/views/ops/DataManagementView.vue"),
    meta: { title: "数据管理", roles: [ROLE_ADMIN] },
  },
  {
    path: "data-management/agents",
    name: "governance-agents",
    component: () => import("@/views/ops/AgentManageView.vue"),
    meta: { title: "Agent 管理", roles: [ROLE_ADMIN] },
  },
  {
    path: "data-management/prompts",
    name: "governance-prompts",
    component: () => import("@/views/ops/PromptManageView.vue"),
    meta: { title: "Prompt 管理", roles: [ROLE_ADMIN] },
  },
  {
    path: "data-management/intent-routes",
    name: "governance-intent-routes",
    component: () => import("@/views/ops/IntentRouteView.vue"),
    meta: { title: "意图路由配置", roles: [ROLE_ADMIN] },
  },
  {
    path: "data-management/inspection-specs",
    name: "governance-inspection-specs",
    component: () => import("@/views/admin/InspectionSpecView.vue"),
    meta: { title: "检测标准", roles: [ROLE_ADMIN] },
  },
];
