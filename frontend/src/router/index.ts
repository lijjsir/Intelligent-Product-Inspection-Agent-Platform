import { createRouter, createWebHistory } from "vue-router";
import { isAdminWorkspaceRoute } from "@/utils/admin-workspace";
import { useAuthStore } from "@/stores/auth.store";
import { appRoutes } from "@/router/routes/app.routes";
import { opsRoutes } from "@/router/routes/ops.routes";
import { governanceRoutes } from "@/router/routes/governance.routes";
import { permissionsForRoute, ordinaryUserTaskRedirect } from "@/utils/permission-routes";

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
    path: "/app",
    component: () => import("@/layouts/AppLayout.vue"),
    children: appRoutes,
    meta: { requiresAuth: true },
  },
  {
    path: "/ops",
    component: () => import("@/layouts/AppLayout.vue"),
    children: opsRoutes,
    meta: { requiresAuth: true },
  },
  {
    path: "/governance",
    component: () => import("@/layouts/AppLayout.vue"),
    children: governanceRoutes,
    meta: { requiresAuth: true },
  },
  {
    path: "/users",
    component: () => import("@/layouts/AppLayout.vue"),
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        name: "users",
        component: () => import("@/views/UserListView.vue"),
        meta: { title: "用户管理", roles: ["admin"] },
      },
    ],
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/app/dashboard",
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();

  if (to.meta.requiresAuth && !auth.isAuthed) {
    return { path: "/login" };
  }

  if (to.meta.requiresAuth && auth.isAuthed) {
    await auth.refreshPermissions();
  }

  if (to.meta.requiresAuth && auth.isAuthed && auth.primaryRole === "admin" && !isAdminWorkspaceRoute(to.path)) {
    return { path: auth.resolveDefaultRoute() };
  }

  if (auth.isAuthed && auth.primaryRole === "user") {
    const redirect = ordinaryUserTaskRedirect(to.path, String(to.query.task_id || ""));
    if (redirect) return { path: redirect, query: to.path === "/app/export" && to.query.task_id ? { report: "1" } : {} };
  }

  if (auth.isAuthed && ["/app", "/ops", "/governance", "/app/dashboard"].includes(to.path)) {
    return { path: auth.resolveDefaultRoute() };
  }

  // 登录/注册页始终可访问，不自动跳走（方便切换账号或重启后重新登录）

  // Check route meta role restrictions
  const routeRoles = to.meta.roles as string[] | undefined;
  const routePermissions = permissionsForRoute(to.path);
  if (routePermissions && auth.effectivePermissions !== null) {
    return auth.hasPermission(routePermissions) ? true : { path: auth.resolveDefaultRoute() };
  }
  if (routeRoles && routeRoles.length) {
    const currentRoles = auth.roles.length ? auth.roles : [auth.role];
    const hasAccess = routeRoles.some((r) => currentRoles.includes(r));
    if (!hasAccess) {
      return { path: auth.resolveDefaultRoute() };
    }
  }

  return true;
});

export default router;
