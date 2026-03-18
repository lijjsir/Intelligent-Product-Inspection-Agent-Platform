import { createRouter, createWebHistory } from "vue-router";
import AppLayout from "@/layouts/AppLayout.vue";
import AuthLayout from "@/layouts/AuthLayout.vue";
import LoginView from "@/views/LoginView.vue";
import RegisterView from "@/views/RegisterView.vue";
import DashboardView from "@/views/DashboardView.vue";
import TaskListView from "@/views/TaskListView.vue";
import TaskDetailView from "@/views/TaskDetailView.vue";
import ResultDetailView from "@/views/ResultDetailView.vue";
import StabilityDetailView from "@/views/StabilityDetailView.vue";
import AlertListView from "@/views/AlertListView.vue";
import AnalyticsView from "@/views/AnalyticsView.vue";
import UserListView from "@/views/UserListView.vue";
import { useAuthStore } from "@/stores/auth.store";

const routes = [
  {
    path: "/login",
    component: AuthLayout,
    children: [
      {
        path: "",
        name: "login",
        component: LoginView,
      },
    ],
  },
  {
    path: "/register",
    component: AuthLayout,
    children: [
      {
        path: "",
        name: "register",
        component: RegisterView,
      },
    ],
  },
  {
    path: "/",
    component: AppLayout,
    children: [
      { path: "", name: "dashboard", component: DashboardView },
      { path: "tasks", name: "tasks", component: TaskListView },
      { path: "tasks/:id", name: "task-detail", component: TaskDetailView },
      { path: "results/:id", name: "result-detail", component: ResultDetailView },
      { path: "stability/:id", name: "stability-detail", component: StabilityDetailView },
      { path: "alerts", name: "alerts", component: AlertListView },
      { path: "analytics", name: "analytics", component: AnalyticsView },
      { path: "users", name: "users", component: UserListView },
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
  console.log("路由守卫 - 目标路径:", to.path);
  console.log("路由守卫 - 是否需要认证:", to.meta.requiresAuth);
  console.log("路由守卫 - 是否已认证:", auth.isAuthed);
  
  if (to.meta.requiresAuth && !auth.isAuthed) {
    console.log("路由守卫 - 未认证，跳转到登录页");
    return { path: "/login" };
  }
  if ((to.path === "/login" || to.path === "/register") && auth.isAuthed) {
    console.log("路由守卫 - 已认证，跳转到首页");
    return { path: "/" };
  }
  console.log("路由守卫 - 允许通过");
  return true;
});

export default router;
