import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useMenu } from "@/composables/useMenu";
import { useAuthStore } from "@/stores/auth.store";
import {
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_EXPERT,
  ROLE_PLATFORM_OPERATOR,
} from "@/constants/roles";
import { opsRoutes } from "@/router/routes/ops.routes";

function flattenTitles() {
  const { menu } = useMenu();
  return menu.value.flatMap((item) => ("items" in item ? item.items.map((child) => child.title) : [item.title]));
}

describe("useMenu", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("shows shared agent ops entries for platform operators", () => {
    const auth = useAuthStore();
    auth.role = ROLE_PLATFORM_OPERATOR;
    auth.roles = [ROLE_PLATFORM_OPERATOR];

    const titles = flattenTitles();

    expect(titles).toContain("Agent 管理");
    expect(titles).toContain("路由策略");
    expect(titles).toContain("Prompt 管理");
    expect(titles).toContain("RAG 分析");
  });

  it("shows shared agent ops entries for experts", () => {
    const auth = useAuthStore();
    auth.role = ROLE_EXPERT;
    auth.roles = [ROLE_EXPERT];

    const titles = flattenTitles();

    expect(titles).toContain("Agent 管理");
    expect(titles).toContain("路由策略");
    expect(titles).toContain("Prompt 管理");
    expect(titles).toContain("RAG 分析");
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
});
