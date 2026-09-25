import {
  CHAT_ROLES,
  COLLABORATION_ROLES,
  ROLE_ADMIN,
  ROLE_USER,
  ROLE_EXPERT,
  ROLE_PLATFORM_OPERATOR,
  ROLE_ALGORITHM_ENGINEER,
} from "@/constants/roles";

const APP_ROLES = [...CHAT_ROLES];
const COLLAB_APP_ROLES = [...COLLABORATION_ROLES];

export const appRoutes = [
  {
    path: "workbench",
    name: "app-supervision-workbench",
    component: () => import("@/views/supervision/SupervisionWorkbenchView.vue"),
    meta: { title: "质监工作台", roles: [ROLE_USER, ROLE_EXPERT] },
  },
  {
    path: "laboratory",
    name: "app-laboratory",
    component: () => import("@/views/supervision/LaboratoryCenterView.vue"),
    meta: { title: "实验室检测", roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "exposures",
    name: "app-exposures",
    component: () => import("@/views/supervision/SupervisionRecordsView.vue"),
    meta: {
      title: "态势基础数据",
      supervisionKind: "exposures",
      roles: [ROLE_ADMIN, ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR],
    },
  },
  ...[
    "risk-cases",
    "sampling-plans",
    "inspection-sessions",
    "samples",
    "enterprises",
    "devices",
  ].map((kind) => ({
    path: kind,
    name: `app-${kind}`,
    component: () => import("@/views/supervision/SupervisionRecordsView.vue"),
    meta: {
      title: (
        {
          "risk-cases": "舆情监测",
          "sampling-plans": "监督抽查",
          "inspection-sessions": "检测会话",
          samples: "样品登记",
          enterprises: "监管对象",
          devices: "设备资源",
        } as Record<string, string>
      )[kind],
      supervisionKind: kind,
      roles:
        kind === "devices"
          ? [
              ROLE_ADMIN,
              ROLE_PLATFORM_OPERATOR,
              ROLE_ALGORITHM_ENGINEER,
              "app_developer",
              ROLE_USER,
              ROLE_EXPERT,
            ]
          : [ROLE_ADMIN, ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR],
    },
  })),
  {
    path: "quality-analytics",
    name: "app-quality-analytics",
    component: () => import("@/views/supervision/SupervisionAnalyticsView.vue"),
    meta: {
      title: "市场监控",
      roles: [ROLE_USER, ROLE_EXPERT, ROLE_ADMIN, ROLE_PLATFORM_OPERATOR],
    },
  },
  {
    path: "dashboard",
    name: "app-dashboard",
    redirect: { name: "app-chat" },
    meta: { title: "工作台概览", roles: APP_ROLES },
  },
  {
    path: "chat",
    name: "app-chat",
    component: () => import("@/views/ChatView.vue"),
    meta: { title: "AI 对话", roles: APP_ROLES },
  },
  {
    path: "meetings",
    name: "app-meetings",
    component: () => import("@/views/MeetingRoomView.vue"),
    meta: { title: "聊天会议室", roles: COLLAB_APP_ROLES },
  },
  {
    path: "collab",
    name: "app-collab",
    component: () => import("@/views/CollabMessagesView.vue"),
    meta: { title: "协作中心", roles: COLLAB_APP_ROLES },
  },
  {
    path: "rag-spaces",
    name: "app-rag-spaces",
    component: () => import("@/views/RagSpaceView.vue"),
    meta: { title: "RAG 空间", roles: [ROLE_ADMIN, ROLE_EXPERT] },
  },
  {
    path: "tasks",
    name: "app-tasks",
    component: () => import("@/views/TaskListView.vue"),
    meta: {
      title: "任务管理",
      roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER],
    },
  },
  {
    path: "tasks/:id",
    name: "app-task-detail",
    component: () => import("@/views/TaskDetailView.vue"),
    meta: { roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER] },
  },
  {
    path: "results",
    name: "app-results",
    component: () => import("@/views/ResultListView.vue"),
    meta: {
      title: "检测结果",
      roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR],
    },
  },
  {
    path: "results/:id",
    name: "app-result-detail",
    component: () => import("@/views/ResultDetailView.vue"),
    meta: { title: "检测结果详情", roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "results/:task_id/evidence",
    name: "app-evidence",
    component: () => import("@/views/EvidenceView.vue"),
    meta: { title: "证据溯源", roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "feedbacks",
    name: "app-feedbacks",
    component: () => import("@/views/quality/FeedbackCenterView.vue"),
    meta: { title: "异常反馈", roles: APP_ROLES },
  },
  {
    path: "stability",
    name: "app-stability-overview",
    component: () => import("@/views/StabilityOverviewView.vue"),
    meta: { title: "稳定性监控", roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "stability/:id",
    name: "app-stability-detail",
    component: () => import("@/views/StabilityDetailView.vue"),
    meta: { roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "alerts",
    name: "app-alerts",
    redirect: "/app/stability?tab=alerts",
    meta: { roles: [ROLE_USER, ROLE_EXPERT, ROLE_PLATFORM_OPERATOR] },
  },
  {
    path: "export",
    name: "app-export",
    component: () => import("@/views/ReportExportView.vue"),
    meta: { title: "报告导出", roles: APP_ROLES },
  },
  {
    path: "profile",
    name: "app-profile",
    component: () => import("@/views/ProfileView.vue"),
    meta: { title: "个人设置" },
  },
];
