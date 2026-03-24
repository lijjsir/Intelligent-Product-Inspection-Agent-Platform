import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";
import { adminRoutes } from "@/router/routes/admin.routes";
import { qualityRoutes } from "@/router/routes/quality.routes";
import { ROLE_SUPER_ADMIN } from "@/constants/roles";

const routes = [
  {
    path: "/login",
    component: () => import("@/layouts/AuthLayout.vue"),
    children: [
      {
        path: "",
        name: "login",
        component: () => import("@/views/LoginView.vue"),
      },
    ],
  },
  {
    path: "/register",
    component: () => import("@/layouts/AuthLayout.vue"),
    children: [
      {
        path: "",
        name: "register",
        component: () => import("@/views/RegisterView.vue"),
      },
    ],
  },
  {
    path: "/",
    component: () => import("@/layouts/AppLayout.vue"),
    children: [
      { path: "", name: "dashboard", component: () => import("@/views/DashboardView.vue") },
      { path: "tasks", name: "tasks", component: () => import("@/views/TaskListView.vue") },
      { path: "tasks/:id", name: "task-detail", component: () => import("@/views/TaskDetailView.vue") },
      { path: "results", name: "results", component: () => import("@/views/ResultListView.vue") },
      { path: "results/:id", name: "result-detail", component: () => import("@/views/ResultDetailView.vue") },
      { path: "stability/:id", name: "stability-detail", component: () => import("@/views/StabilityDetailView.vue") },
      { path: "alerts", name: "alerts", component: () => import("@/views/AlertListView.vue") },
      { path: "analytics", name: "analytics", component: () => import("@/views/AnalyticsView.vue") },
      { path: "users", name: "users", component: () => import("@/views/UserListView.vue") },
      { path: "profile", name: "profile", component: () => import("@/views/ProfileView.vue") },
      ...adminRoutes,
      ...qualityRoutes,
    ],
    meta: { requiresAuth: true },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const auth = useAuthStore();

  if (to.meta.requiresAuth && !auth.isAuthed) {
    return { path: "/login" };
  }
  const roles = to.meta.roles as string[] | undefined;
  if (roles && auth.role !== ROLE_SUPER_ADMIN && !roles.includes(auth.role)) {
    return { path: "/" };
  }
  if ((to.path === "/login" || to.path === "/register") && auth.isAuthed) {
    return { path: "/" };
  }
  return true;
});

export default router;
