import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";
import { appRoutes } from "@/router/routes/app.routes";
import { opsRoutes } from "@/router/routes/ops.routes";
import { governanceRoutes } from "@/router/routes/governance.routes";
import { ROLE_ADMIN, ROLE_USER, normalizeRole } from "@/constants/roles";

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

router.beforeEach((to) => {
  const auth = useAuthStore();

  if (to.meta.requiresAuth && !auth.isAuthed) {
    return { path: "/login" };
  }

  const primaryRole = normalizeRole(auth.primaryRole);
  if (auth.isAuthed && primaryRole === ROLE_USER && !["/app/chat", "/app/rag-spaces"].includes(to.path)) {
    return { path: "/app/chat" };
  }

  const roles = to.meta.roles as string[] | undefined;
  const currentRoles = auth.roles.length ? auth.roles : [auth.role];
  const normalizedRoles = currentRoles.map(normalizeRole);
  if (roles) {
    const normalizedRequiredRoles = roles.map(normalizeRole);
    const hasMatchedRole = normalizedRequiredRoles.some((role) => normalizedRoles.includes(role));
    const isUserOnlyRoute = normalizedRequiredRoles.includes(ROLE_USER);
    if (isUserOnlyRoute && !hasMatchedRole) {
      return { path: "/app/dashboard" };
    }
    if (!isUserOnlyRoute && !normalizedRoles.includes(ROLE_ADMIN) && !hasMatchedRole) {
      return { path: "/app/dashboard" };
    }
  }
  if ((to.path === "/login" || to.path === "/register") && auth.isAuthed) {
    return { path: auth.resolveDefaultRoute() };
  }
  return true;
});

export default router;
