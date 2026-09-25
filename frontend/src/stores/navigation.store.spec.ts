import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "@/stores/auth.store";
import { useNavigationStore } from "@/stores/navigation.store";
import { isMenuGroup, useMenu } from "@/composables/useMenu";
import { appRoutes } from "@/router/routes/app.routes";
import { opsRoutes } from "@/router/routes/ops.routes";
import { governanceRoutes } from "@/router/routes/governance.routes";

describe("navigation session choices", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    setActivePinia(createPinia());
  });

  it("keeps both groups open across standalone pages and layout remounts", () => {
    const navigation = useNavigationStore();
    navigation.revealGroups(["系统治理"]);
    navigation.toggleGroup("基础资料");
    navigation.revealGroups([]); // Meeting rooms and collaboration have no group.
    navigation.revealGroups(["基础资料"]);
    expect(useNavigationStore().expandedGroups).toEqual(["系统治理", "基础资料"]);
  });

  it("respects manual collapse when the active route is still inside the group", () => {
    const navigation = useNavigationStore();
    navigation.revealGroups(["基础资料", "系统治理"]);
    navigation.toggleGroup("基础资料");
    navigation.revealGroups([]);
    navigation.revealGroups(["基础资料"]);
    expect(navigation.expandedGroups).toEqual(["系统治理"]);
    navigation.toggleGroup("基础资料");
    expect(navigation.expandedGroups).toEqual(["系统治理", "基础资料"]);
  });

  it("resets choices on logout and account changes, while token refresh keeps them", () => {
    const auth = useAuthStore();
    auth.token = "session";
    auth.userId = "admin-1";
    const navigation = useNavigationStore();
    navigation.toggleGroup("系统治理");
    auth.token = "refreshed-session";
    expect(navigation.expandedGroups).toEqual(["系统治理"]);
    auth.userId = "admin-2";
    expect(navigation.expandedGroups).toEqual([]);
    navigation.toggleGroup("基础资料");
    auth.logout();
    expect(navigation.expandedGroups).toEqual([]);
  });

  it.each([
    ["admin", "/governance/admin/users"],
    ["app_developer", "/ops/agents"],
    ["platform_operator", "/ops/dashboard"],
    ["algorithm_engineer", "/ops/data/import"],
    ["expert", "/app/chat"],
    ["user", "/app/chat"],
  ])("opens a visible permitted menu page for %s at login", (role, landingPath) => {
    const auth = useAuthStore();
    auth.role = role;
    auth.roles = [role];
    expect(auth.resolveDefaultRoute()).toBe(landingPath);
    const { menu } = useMenu();
    const paths = menu.value.flatMap((entry) =>
      isMenuGroup(entry) ? entry.items.map((item) => item.path) : [entry.path],
    );
    expect(paths).toContain(landingPath);
    const [prefix, routes] = landingPath.startsWith("/governance/")
      ? (["/governance/", governanceRoutes] as const)
      : landingPath.startsWith("/ops/")
        ? (["/ops/", opsRoutes] as const)
        : (["/app/", appRoutes] as const);
    const route = routes.find((item) => `${prefix}${item.path}` === landingPath);
    expect(route?.meta?.roles).toContain(role);
  });
});
