export const appRoutes = [
  { path: "dashboard", name: "app-dashboard", component: () => import("@/views/DashboardView.vue") },
  { path: "chat", name: "app-chat", component: () => import("@/views/ChatView.vue"), meta: { title: "智能对话" } },
  { path: "rag-spaces", name: "app-rag-spaces", component: () => import("@/views/RagSpaceView.vue"), meta: { title: "知识库" } },
  { path: "tasks", name: "app-tasks", component: () => import("@/views/TaskListView.vue"), meta: { title: "任务管理" } },
  { path: "tasks/:id", name: "app-task-detail", component: () => import("@/views/TaskDetailView.vue") },
  { path: "results", name: "app-results", component: () => import("@/views/ResultListView.vue") },
  { path: "results/:id", name: "app-result-detail", component: () => import("@/views/ResultDetailView.vue") },
  { path: "stability", name: "app-stability-overview", component: () => import("@/views/StabilityOverviewView.vue") },
  { path: "stability/:id", name: "app-stability-detail", component: () => import("@/views/StabilityDetailView.vue") },
  { path: "alerts", name: "app-alerts", redirect: "/app/stability?tab=alerts" },
  {
    path: "feedbacks",
    name: "app-feedbacks",
    component: () => import("@/views/quality/FeedbackListView.vue"),
    meta: { title: "反馈流水" },
  },
  { path: "profile", name: "app-profile", component: () => import("@/views/ProfileView.vue") },
];
