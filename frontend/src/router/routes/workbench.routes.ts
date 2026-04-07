export const workbenchRoutes = [
  {
    path: "",
    name: "workbench",
    component: () => import("@/views/WorkbenchView.vue"),
    redirect: "/workbench/chat",
    meta: { title: "聊天" },
    children: [
      { path: "chat", name: "workbench-chat", component: () => import("@/views/ChatView.vue"), meta: { title: "智能对话" } },
      { path: "rag-spaces", name: "workbench-rag-spaces", component: () => import("@/views/RagSpaceView.vue"), meta: { title: "知识库" } },
    ],
  },
];
