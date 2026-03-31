import { ROLE_ADMIN, ROLE_ANALYST } from "@/constants/roles";

export const governanceRoutes = [
  {
    path: "quality/report",
    name: "governance-quality-report",
    component: () => import("@/views/quality/QualityReportView.vue"),
    meta: { roles: [ROLE_ADMIN, ROLE_ANALYST] },
  },
  {
    path: "quality/tracing",
    name: "governance-quality-tracing",
    component: () => import("@/views/quality/QualityTracingView.vue"),
    meta: { roles: [ROLE_ADMIN, ROLE_ANALYST] },
  },
  {
    path: "quality/feedbacks",
    name: "governance-quality-feedbacks",
    component: () => import("@/views/quality/FeedbackListView.vue"),
    meta: { roles: [ROLE_ADMIN, ROLE_ANALYST] },
  },
  {
    path: "admin/inspection-specs",
    name: "governance-admin-inspection-specs",
    component: () => import("@/views/admin/InspectionSpecView.vue"),
    meta: { roles: [ROLE_ADMIN, ROLE_ANALYST] },
  },
  {
    path: "admin/models",
    name: "governance-admin-models",
    component: () => import("@/views/admin/ModelConfigView.vue"),
    meta: { roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/billing",
    name: "governance-admin-billing",
    component: () => import("@/views/admin/TokenBillingView.vue"),
    meta: { roles: [ROLE_ADMIN] },
  },
  {
    path: "admin/gpu",
    name: "governance-admin-gpu",
    component: () => import("@/views/admin/GpuMonitorView.vue"),
    meta: { roles: [ROLE_ADMIN] },
  },
];
