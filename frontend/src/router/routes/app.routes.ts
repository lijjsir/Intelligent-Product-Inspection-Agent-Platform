export const appRoutes = [
  { path: "dashboard", name: "app-dashboard", component: () => import("@/views/DashboardView.vue") },
  { path: "tasks", name: "app-tasks", component: () => import("@/views/TaskListView.vue") },
  { path: "tasks/:id", name: "app-task-detail", component: () => import("@/views/TaskDetailView.vue") },
  { path: "results", name: "app-results", component: () => import("@/views/ResultListView.vue") },
  { path: "results/:id", name: "app-result-detail", component: () => import("@/views/ResultDetailView.vue") },
  { path: "stability", name: "app-stability-overview", component: () => import("@/views/StabilityOverviewView.vue") },
  { path: "stability/:id", name: "app-stability-detail", component: () => import("@/views/StabilityDetailView.vue") },
  { path: "alerts", name: "app-alerts", component: () => import("@/views/AlertListView.vue") },
  { path: "analytics", name: "app-analytics", component: () => import("@/views/AnalyticsView.vue") },
  { path: "users", name: "app-users", component: () => import("@/views/UserListView.vue") },
  { path: "profile", name: "app-profile", component: () => import("@/views/ProfileView.vue") },
];
