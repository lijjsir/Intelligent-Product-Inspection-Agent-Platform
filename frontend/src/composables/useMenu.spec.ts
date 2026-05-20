import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useMenu } from "@/composables/useMenu";
import { useAuthStore } from "@/stores/auth.store";
import {
  ROLE_ADMIN,
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

  it("shows agent ops entries for platform operators", () => {
    const auth = useAuthStore();
    auth.role = ROLE_PLATFORM_OPERATOR;
    auth.roles = [ROLE_PLATFORM_OPERATOR];

    const titles = flattenTitles();

    expect(titles).toContain("Agent 管理");
    expect(titles).toContain("路由策略");
    expect(titles).toContain("Prompt 管理");
    expect(titles).toContain("RAG 分析");
  });

  it("shows agent ops entries for experts", () => {
    const auth = useAuthStore();
    auth.role = ROLE_EXPERT;
    auth.roles = [ROLE_EXPERT];

    const titles = flattenTitles();

    expect(titles).toContain("Agent 管理");
    expect(titles).toContain("路由策略");
    expect(titles).toContain("Prompt 管理");
    expect(titles).toContain("RAG 分析");
  });

  it("allows non-developer ops roles to access agent ops routes", () => {
    const criticalRoutes = opsRoutes.filter((route) =>
      ["ops-agents", "ops-agents-intent-routes", "ops-prompts", "ops-rag"].includes(String(route.name)),
    );

    for (const route of criticalRoutes) {
      expect(route.meta?.roles).toContain(ROLE_ADMIN);
      expect(route.meta?.roles).toContain(ROLE_PLATFORM_OPERATOR);
      expect(route.meta?.roles).toContain(ROLE_EXPERT);
    }
  });
});
