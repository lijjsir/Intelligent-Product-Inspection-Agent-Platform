import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "@/stores/auth.store";
import { useMenu } from "@/composables/useMenu";
import { ADMIN_MENU_GROUPS, isAdminWorkspaceRoute } from "./admin-workspace";
import { roleMenuPaths } from "./role-navigation";
import { permissionsForRoute } from "./permission-routes";

describe("administrator governance workspace", () => {
  beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setActivePinia(createPinia()); });
  it("never expands the administrator menu even when every permission is granted", () => {
    const auth = useAuthStore(); auth.token = "session"; auth.role = "admin"; auth.roles = ["admin"];
    auth.effectivePermissions = [...new Set([
      ...["admin", "user", "expert", "algorithm_engineer", "app_developer", "platform_operator"].flatMap(role => roleMenuPaths(role).flatMap(path => permissionsForRoute(path) || [])),
      ...ADMIN_MENU_GROUPS.flatMap(group => group.items.flatMap(item => permissionsForRoute(item.path) || [])),
    ])];
    const { menu } = useMenu();
    expect(menu.value.map(item => item.title)).toEqual(["组织与权限", "质监基础", "标准管理", "规则与复核", "知识准入与发布", "审计与审批", "个人设置"]);
    expect(menu.value.flatMap(item => "items" in item ? item.items.map(child => child.path) : [item.path])).toEqual([
      ...ADMIN_MENU_GROUPS.flatMap(group => group.items.map(item => item.path)), "/app/profile",
    ]);
    expect(menu.value.some(item => item.title === "已授权功能")).toBe(false);
  });
  it("rejects technical, business, and shared collaboration page destinations", () => {
    for (const path of ["/app/tasks", "/app/results", "/app/chat", "/app/quality-data", "/app/meetings", "/app/collab",
      "/ops/data/import", "/ops/models/config", "/ops/tools", "/ops/agents", "/ops/prompts", "/ops/billing",
      "/governance/admin/models", "/governance/admin/gpu", "/governance/quality/analysis-center", "/governance/admin/quality-data-sources"]) {
      expect(isAdminWorkspaceRoute(path), path).toBe(false);
    }
  });
  it("retains governance pages, their details, profile, and old catalog links", () => {
    for (const group of ADMIN_MENU_GROUPS) for (const item of group.items) {
      expect(isAdminWorkspaceRoute(item.path)).toBe(true);
      expect(isAdminWorkspaceRoute(`${item.path}/detail?tab=history`)).toBe(true);
    }
    expect(isAdminWorkspaceRoute("/governance/admin/product-master")).toBe(true);
    expect(isAdminWorkspaceRoute("/app/profile")).toBe(true);
    expect(isAdminWorkspaceRoute("/governance/admin/users-injected")).toBe(false);
  });
  it("exposes inspection gates only when the administrator has read permission", () => {
    const auth = useAuthStore(); auth.token = "session"; auth.role = "admin"; auth.roles = ["admin"];
    const path = "/governance/admin/ai-review-gates";
    const paths = () => useMenu().menu.value.flatMap(item => "items" in item ? item.items.map(child => child.path) : [item.path]);
    auth.effectivePermissions = ["inspection_spec_read"];
    expect(isAdminWorkspaceRoute(path)).toBe(true);
    expect(paths()).toContain(path);
    auth.effectivePermissions = ["inspection_standard_library_read"];
    expect(paths()).not.toContain(path);
  });
  it("never chooses a developer or business fallback for an administrator", () => {
    const auth = useAuthStore(); auth.token = "session"; auth.role = "admin"; auth.roles = ["admin"];
    auth.effectivePermissions = ["chat", "task", "tool", "dataset"];
    expect(isAdminWorkspaceRoute(auth.resolveDefaultRoute())).toBe(true);
  });
  it("does not invent an expert rule-authoring duty", () => {
    const auth = useAuthStore(); auth.role = "expert"; auth.roles = ["expert"];
    const paths = useMenu().menu.value.flatMap(item => "items" in item ? item.items.map(child => child.path) : [item.path]);
    expect(paths).not.toContain("/app/standard-rules");
    expect(paths).not.toContain("/app/risk-policies");
  });
});
