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
} from "@/constants/roles";
import { appRoutes } from "@/router/routes/app.routes";
import { opsRoutes } from "@/router/routes/ops.routes";

function flattenTitles() {
  const { menu } = useMenu();
  return menu.value.flatMap((item) => ("items" in item ? item.items.map((child) => child.title) : [item.title]));
}

function flattenPaths() {
  const { menu } = useMenu();
  return menu.value.flatMap((item) => ("items" in item ? item.items.map((child) => child.path) : [item.path]));
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

  it("shows task management entry for algorithm engineers", () => {
    const auth = useAuthStore();
    auth.role = ROLE_ALGORITHM_ENGINEER;
    auth.roles = [ROLE_ALGORITHM_ENGINEER];

    const titles = flattenTitles();
    const paths = flattenPaths();

    expect(titles).toContain("任务管理");
    expect(paths).toContain("/app/tasks");
  });

  it("shows collaboration entry points to non-expert workbench roles", () => {
    const auth = useAuthStore();

    for (const role of [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER]) {
      auth.role = role;
      auth.roles = [role];

      const paths = flattenPaths();

      expect(paths).toContain("/app/meetings");
      expect(paths).toContain("/app/collab");
    }
  });

  it("keeps collaboration entries at the top while chat stays first for app users", () => {
    const auth = useAuthStore();

    auth.role = ROLE_EXPERT;
    auth.roles = [ROLE_EXPERT];
    expect(flattenPaths().slice(0, 3)).toEqual(["/app/chat", "/app/meetings", "/app/collab"]);

    for (const role of [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER]) {
      auth.role = role;
      auth.roles = [role];

      expect(flattenPaths().slice(0, 2)).toEqual(["/app/meetings", "/app/collab"]);
    }
  });

  it("allows every first-class role into meeting rooms and collaboration messages", () => {
    const meetingRoute = appRoutes.find((route) => route.name === "app-meetings");
    const collabRoute = appRoutes.find((route) => route.name === "app-collab");

    for (const role of [ROLE_ADMIN, ROLE_APP_DEVELOPER, ROLE_PLATFORM_OPERATOR, ROLE_ALGORITHM_ENGINEER, ROLE_EXPERT]) {
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
    expect(titles).toContain("质检门槛查看");
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
    expect(toolGroup && "items" in toolGroup ? toolGroup.items.map((item) => item.title) : []).toEqual([
      "工具总览",
      "工具库",
      "外部导入",
      "Agent 绑定",
      "执行监控",
    ]);
  });

  it("surfaces alert rule governance for admins instead of the ops alert page", () => {
    const auth = useAuthStore();
    auth.role = ROLE_ADMIN;
    auth.roles = [ROLE_ADMIN];

    const titles = flattenTitles();
    const paths = flattenPaths();

    expect(titles).toContain("告警规则");
    expect(titles).not.toContain("告警管理");
    expect(paths).toContain("/governance/admin/product-master");
    expect(paths).toContain("/governance/admin/alert-rules");
  });

  it("exposes the governance analytics center in admin navigation", () => {
    const auth = useAuthStore();
    auth.role = ROLE_ADMIN;
    auth.roles = [ROLE_ADMIN];

    expect(flattenPaths()).toContain("/governance/quality/analysis-center");
  });

  it("keeps tool management routes accessible to admins", () => {
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
