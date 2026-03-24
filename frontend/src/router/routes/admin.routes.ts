import { ROLE_PLATFORM_ADMIN, ROLE_SUPER_ADMIN } from "@/constants/roles";

export const adminRoutes = [
  {
    path: "admin/models",
    name: "admin-models",
    component: () => import("@/views/admin/ModelConfigView.vue"),
    meta: { roles: [ROLE_PLATFORM_ADMIN, ROLE_SUPER_ADMIN] },
  },
  {
    path: "admin/billing",
    name: "admin-billing",
    component: () => import("@/views/admin/TokenBillingView.vue"),
    meta: { roles: [ROLE_PLATFORM_ADMIN, ROLE_SUPER_ADMIN] },
  },
  {
    path: "admin/gpu",
    name: "admin-gpu",
    component: () => import("@/views/admin/GpuMonitorView.vue"),
    meta: { roles: [ROLE_PLATFORM_ADMIN, ROLE_SUPER_ADMIN] },
  },
];
