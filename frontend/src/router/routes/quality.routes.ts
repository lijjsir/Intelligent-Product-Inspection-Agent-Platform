import { ROLE_AI_QUALITY, ROLE_SUPER_ADMIN } from "@/constants/roles";

export const qualityRoutes = [
  {
    path: "quality/report",
    name: "quality-report",
    component: () => import("@/views/quality/QualityReportView.vue"),
    meta: { roles: [ROLE_AI_QUALITY, ROLE_SUPER_ADMIN] },
  },
  {
    path: "quality/tracing",
    name: "quality-tracing",
    component: () => import("@/views/quality/QualityTracingView.vue"),
    meta: { roles: [ROLE_AI_QUALITY, ROLE_SUPER_ADMIN] },
  },
  {
    path: "quality/feedbacks",
    name: "quality-feedbacks",
    component: () => import("@/views/quality/FeedbackListView.vue"),
    meta: { roles: [ROLE_AI_QUALITY, ROLE_SUPER_ADMIN] },
  },
];
