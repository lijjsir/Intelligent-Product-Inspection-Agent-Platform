import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useMenu } from "@/composables/useMenu";
import { useAuthStore } from "@/stores/auth.store";
import {
  ROLE_ADMIN,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_APP_DEVELOPER,
  ROLE_EXPERT,
  ROLE_PLATFORM_OPERATOR,
  ROLE_USER,
} from "@/constants/roles";
import { appRoutes } from "@/router/routes/app.routes";
import { opsRoutes } from "@/router/routes/ops.routes";

function flattenTitles() {
  const { menu } = useMenu();
  return menu.value.flatMap((item) =>
    "items" in item ? item.items.map((child) => child.title) : [item.title],
  );
}

function flattenPaths() {
  const { menu } = useMenu();
  return menu.value.flatMap((item) =>
    "items" in item ? item.items.map((child) => child.path) : [item.path],
  );
}

describe("useMenu", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("keeps agent ops entries scoped to app developers", () => {
    const auth = useAuthStore();
    auth.role = ROLE_APP_DEVELOPER;
    auth.roles = [ROLE_APP_DEVELOPER];

    const titles = flattenTitles();

    expect(titles).toContain("Agent 管理");
    expect(titles).toContain("路由策略");
    expect(titles).toContain("Prompt 管理");
    expect(titles).toContain("RAG 分析");
  });

  it("does not expose developer agent ops entries to platform operators or experts", () => {
    const auth = useAuthStore();
    auth.role = ROLE_PLATFORM_OPERATOR;
    auth.roles = [ROLE_PLATFORM_OPERATOR];

    expect(flattenTitles()).not.toContain("Prompt 管理");

    auth.role = ROLE_EXPERT;
    auth.roles = [ROLE_EXPERT];

    expect(flattenTitles()).not.toContain("Prompt 管理");
  });

  it("keeps algorithm engineers in training and explicitly authorized data workflows", () => {
    const auth = useAuthStore();
    auth.role = ROLE_ALGORITHM_ENGINEER;
    auth.roles = [ROLE_ALGORITHM_ENGINEER];

    const titles = flattenTitles();
    const paths = flattenPaths();

    expect(titles).not.toContain("任务管理");
    expect(paths).not.toContain("/app/tasks");
    expect(paths).toContain("/ops/training/jobs");
    expect(paths).toContain("/ops/data/business-samples");
  });

  it("shows collaboration entry points to non-expert workbench roles", () => {
    const auth = useAuthStore();

    for (const role of [
      ROLE_APP_DEVELOPER,
      ROLE_PLATFORM_OPERATOR,
      ROLE_ALGORITHM_ENGINEER,
    ]) {
      auth.role = role;
      auth.roles = [role];

      const paths = flattenPaths();

      expect(paths).toContain("/app/meetings");
      expect(paths).toContain("/app/collab");
    }
  });

  it("names the collaboration work queue as collaboration center", () => {
    const auth = useAuthStore();
    auth.role = ROLE_EXPERT;
    auth.roles = [ROLE_EXPERT];

    expect(flattenTitles()).toContain("协同中心");
    expect(flattenTitles()).not.toContain("协作消息");
    expect(appRoutes.find((route) => route.name === "app-collab")?.meta?.title).toBe("协作中心");
  });

  it("puts the quality-supervision workbench before business flow for experts", () => {
    const auth = useAuthStore();

    auth.role = ROLE_EXPERT;
    auth.roles = [ROLE_EXPERT];
    expect(flattenPaths().slice(0, 4)).toEqual([
      "/app/chat",
      "/app/workbench",
      "/app/quality-data",
      "/app/quality-analytics",
    ]);

    for (const role of [
      ROLE_APP_DEVELOPER,
      ROLE_PLATFORM_OPERATOR,
      ROLE_ALGORITHM_ENGINEER,
    ]) {
      auth.role = role;
      auth.roles = [role];

      expect(flattenPaths().slice(0, 2)).toEqual(["/app/meetings", "/app/collab"]);
    }
  });

  it("keeps expert tasks and results grouped with supervision features", () => {
    const auth = useAuthStore();
    auth.role = ROLE_EXPERT;
    auth.roles = [ROLE_EXPERT];
    expect(flattenTitles()).not.toContain("数据接入");
    expect(flattenTitles()).toContain("风险研判");
    expect(flattenTitles()).toContain("实验室检测");
    expect(flattenTitles()).toContain("检测任务");
    expect(flattenTitles()).toContain("检测结果");

    const { menu } = useMenu();
    const quality = menu.value.find(item => 'items' in item && item.title==='质量监督');
    expect(quality && 'items' in quality ? quality.items.map(item=>item.title) : []).toEqual(['数据采集','市场监控','风险研判','监督抽查','协同中心','报告中心']);
    const taskResult = menu.value.find((item) => "items" in item && item.title === "任务与结果");
    expect(taskResult && "items" in taskResult ? taskResult.items : []).toEqual([
      { title: "检测任务", path: "/app/tasks" },
      { title: "检测结果", path: "/app/results" },
    ]);
  });

  it("keeps ordinary-user navigation focused on chat, personal tasks and settings", () => {
    const auth = useAuthStore();
    auth.role = ROLE_USER;
    auth.roles = [ROLE_USER];

    expect(flattenTitles()).toEqual(["AI 对话", "任务列表", "检测结果", "个人设置"]);
    expect(flattenPaths()).toEqual(["/app/chat", "/app/tasks", "/app/results", "/app/profile"]);
    const { menu } = useMenu();
    expect(menu.value[1]).toMatchObject({ title: "我的任务", items: [
      { title: "任务列表", path: "/app/tasks" },
      { title: "检测结果", path: "/app/results", activeMatchPaths: ["/app/export"] },
    ] });
  });

  it("limits ordinary-user pages to chat and the personal task flow", () => {
    const allowedNames = new Set([
      "app-dashboard", "app-chat", "app-tasks", "app-task-detail",
      "app-results", "app-result-detail", "app-evidence", "app-export", "app-profile",
    ]);
    for (const route of appRoutes) {
      if (route.meta?.roles) {
        expect(route.meta.roles.includes(ROLE_USER)).toBe(allowedNames.has(route.name));
      }
    }
  });

  it("allows every first-class role into meeting rooms and collaboration messages", () => {
    const meetingRoute = appRoutes.find((route) => route.name === "app-meetings");
    const collabRoute = appRoutes.find((route) => route.name === "app-collab");

    for (const role of [
      ROLE_APP_DEVELOPER,
      ROLE_PLATFORM_OPERATOR,
      ROLE_ALGORITHM_ENGINEER,
      ROLE_EXPERT,
    ]) {
      expect(meetingRoute?.meta?.roles).toContain(role);
      expect(collabRoute?.meta?.roles).toContain(role);
    }
  });

  it("keeps governance and infrastructure tools out of platform operator navigation", () => {
    const auth = useAuthStore();
    auth.role = ROLE_PLATFORM_OPERATOR;
    auth.roles = [ROLE_PLATFORM_OPERATOR];

    const { menu } = useMenu();
    const groupTitles = menu.value.flatMap((item) => ("items" in item ? [item.title] : []));
    const titles = flattenTitles();

    expect(groupTitles).not.toContain("治理工具");
    expect(groupTitles).not.toContain("运维诊断");
    expect(groupTitles).not.toContain("只读巡检");
    expect(titles).toContain("告警管理");
    expect(titles).toContain("Agent 查看");
    expect(titles).toContain("检测执行策略");
    expect(titles).not.toContain("标准条款判定条件");
    expect(titles).toContain("模型观测");
    expect(titles).not.toContain("数据质量");
    expect(titles).not.toContain("业务报表");
    expect(titles).not.toContain("成本分析");
    expect(titles).not.toContain("稳定性查看");
    expect(titles).not.toContain("记忆治理");
    expect(titles).not.toContain("存储/基础设施");
    expect(titles).not.toContain("日志中心");
  });

  it("groups tool management entries under app developer navigation", () => {
    const auth = useAuthStore();
    auth.role = ROLE_APP_DEVELOPER;
    auth.roles = [ROLE_APP_DEVELOPER];

    const { menu } = useMenu();
    const toolGroup = menu.value.find((item) => "items" in item && item.title === "工具管理");

    expect(toolGroup).toBeTruthy();
    expect(
      toolGroup && "items" in toolGroup ? toolGroup.items.map((item) => item.title) : [],
    ).toEqual(["工具总览", "工具库", "外部导入", "Agent 绑定", "执行监控"]);
  });

  it("retains operation approvals while keeping alert operations outside admin", () => {
    const auth = useAuthStore();
    auth.role = ROLE_ADMIN;
    auth.roles = [ROLE_ADMIN];

    const titles = flattenTitles();
    const paths = flattenPaths();

    expect(titles).not.toContain("告警规则");
    expect(titles).not.toContain("告警管理");
    expect(paths).toContain("/governance/admin/quality-products");
    expect(paths).toContain("/governance/admin/approvals");
  });

  it("keeps operational analytics outside the administrator workspace", () => {
    const auth = useAuthStore();
    auth.role = ROLE_ADMIN;
    auth.roles = [ROLE_ADMIN];

    expect(flattenPaths()).not.toContain("/governance/quality/analysis-center");
  });

  it("preserves legacy tool route metadata without listing tools in admin navigation", () => {
    const auth = useAuthStore();
    auth.role = ROLE_ADMIN;
    auth.roles = [ROLE_ADMIN];

    const toolRoutes = opsRoutes.filter((route) =>
      [
        "ops-tools-overview",
        "ops-tools-catalog",
        "ops-tools-import",
        "ops-tools-bindings",
        "ops-tools-executions",
      ].includes(String(route.name)),
    );

    for (const route of toolRoutes) {
      expect(route.meta?.roles).toContain(ROLE_ADMIN);
      expect(route.meta?.roles).toContain(ROLE_APP_DEVELOPER);
    }
  });

  it("allows admins into the shared alert management route", () => {
    const alertRoute = opsRoutes.find((route) => route.name === "ops-alerts");

    expect(alertRoute?.meta?.roles).toContain(ROLE_ADMIN);
    expect(alertRoute?.meta?.roles).toContain(ROLE_PLATFORM_OPERATOR);
  });
});
