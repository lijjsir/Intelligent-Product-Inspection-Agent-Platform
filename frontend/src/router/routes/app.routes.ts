import { ROLE_ADMIN, ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR } from "@/constants/roles";

const APP_ROLES = [ROLE_USER, ROLE_EXPERT];

export const appRoutes = [
  { path: "dashboard", name: "app-dashboard", redirect: { name: "app-chat" }, meta: { title: "工作台概览", roles: APP_ROLES } },
  { path: "chat", name: "app-chat", component: () => import("@/views/ChatView.vue"), meta: { title: "AI 对话", roles: APP_ROLES } },
  { path: "meetings", name: "app-meetings", component: () => import("@/views/MeetingRoomView.vue"), meta: { title: "聊天会议室", roles: APP_ROLES } },
  { path: "rag-spaces", name: "app-rag-spaces", component: () => import("@/views/RagSpaceView.vue"), meta: { title: "RAG 空间", roles: [ROLE_ADMIN, ROLE_EXPERT] } },
  { path: "tasks", name: "app-tasks", component: () => import("@/views/TaskListView.vue"), meta: { title: "任务管理", roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] } },
  { path: "tasks/:id", name: "app-task-detail", component: () => import("@/views/TaskDetailView.vue"), meta: { roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] } },
  { path: "results", name: "app-results", component: () => import("@/views/ResultListView.vue"), meta: { title: "检测结果", roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] } },
  { path: "results/:id", name: "app-result-detail", component: () => import("@/views/ResultDetailView.vue"), meta: { title: "检测结果详情", roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] } },
  { path: "results/:task_id/evidence", name: "app-evidence", component: () => import("@/views/EvidenceView.vue"), meta: { title: "证据溯源", roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] } },
  { path: "feedbacks", name: "app-feedbacks", component: () => import("@/views/quality/FeedbackCenterView.vue"), meta: { title: "异常反馈", roles: APP_ROLES } },
  { path: "stability", name: "app-stability-overview", component: () => import("@/views/StabilityOverviewView.vue"), meta: { title: "稳定性监控", roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] } },
  { path: "stability/:id", name: "app-stability-detail", component: () => import("@/views/StabilityDetailView.vue"), meta: { roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] } },
  { path: "alerts", name: "app-alerts", redirect: "/app/stability?tab=alerts", meta: { roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] } },
  { path: "export", name: "app-export", component: () => import("@/views/ReportExportView.vue"), meta: { title: "报告导出", roles: APP_ROLES } },
  { path: "profile", name: "app-profile", component: () => import("@/views/ProfileView.vue"), meta: { title: "个人设置" } },
];
