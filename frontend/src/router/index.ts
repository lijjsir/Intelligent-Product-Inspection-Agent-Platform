import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";
import { appRoutes } from "@/router/routes/app.routes";
import { opsRoutes } from "@/router/routes/ops.routes";
import { governanceRoutes } from "@/router/routes/governance.routes";

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

  // 登录/注册页始终可访问，不自动跳走（方便切换账号或重启后重新登录）

  // Check route meta role restrictions
  const routeRoles = to.meta.roles as string[] | undefined;
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
