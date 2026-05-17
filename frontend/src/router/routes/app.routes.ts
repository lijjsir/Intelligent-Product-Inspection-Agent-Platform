import { ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER, ROLE_USER, ROLE_EXPERT } from "@/constants/roles";

const NON_END_USER_ROLES = [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER];

export const appRoutes = [
  { path: "dashboard", name: "app-dashboard", component: () => import("@/views/DashboardView.vue") },
  { path: "chat", name: "app-chat", component: () => import("@/views/ChatView.vue"), meta: { title: "AI 检测对话", roles: [ROLE_USER, ROLE_EXPERT] } },
  { path: "rag-spaces", name: "app-rag-spaces", component: () => import("@/views/RagSpaceView.vue"), meta: { title: "RAG 空间", roles: [ROLE_EXPERT] } },
  { path: "tasks", name: "app-tasks", component: () => import("@/views/TaskListView.vue"), meta: { title: "任务管理" } },
  { path: "tasks/:id", name: "app-task-detail", component: () => import("@/views/TaskDetailView.vue") },
  { path: "results", name: "app-results", component: () => import("@/views/ResultListView.vue"), meta: { title: "检测结果" } },
  { path: "results/:id", name: "app-result-detail", component: () => import("@/views/ResultDetailView.vue"), meta: { title: "证据溯源" } },
  { path: "feedbacks", name: "app-feedbacks", component: () => import("@/views/quality/FeedbackListView.vue"), meta: { title: "异常反馈" } },
  { path: "stability", name: "app-stability-overview", component: () => import("@/views/StabilityOverviewView.vue"), meta: { title: "稳定性监控", roles: [...NON_END_USER_ROLES, ROLE_USER, ROLE_EXPERT] } },
  { path: "stability/:id", name: "app-stability-detail", component: () => import("@/views/StabilityDetailView.vue"), meta: { roles: [...NON_END_USER_ROLES, ROLE_USER, ROLE_EXPERT] } },
  { path: "alerts", name: "app-alerts", redirect: "/app/stability?tab=alerts", meta: { roles: [...NON_END_USER_ROLES, ROLE_USER, ROLE_EXPERT] } },
  { path: "export", name: "app-export", component: () => import("@/views/placeholder/PlaceholderPage.vue"), meta: { title: "报告导出", roles: [ROLE_USER, ROLE_EXPERT] } },
  { path: "profile", name: "app-profile", component: () => import("@/views/ProfileView.vue"), meta: { title: "个人设置" } },
];
