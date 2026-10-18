import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { ALL_ROLES } from "@/constants/roles";
import { useAuthStore } from "@/stores/auth.store";
import { useMenu } from "@/composables/useMenu";
import { roleMenuPaths } from "./role-navigation";
import { permissionsForRoute } from "./permission-routes";

const allKeys = [...new Set(ALL_ROLES.flatMap(role => roleMenuPaths(role).flatMap(path => permissionsForRoute(path) || [])))];

describe("role-owned menus", () => {
  beforeEach(() => { sessionStorage.clear(); localStorage.clear(); setActivePinia(createPinia()); });
  it.each(ALL_ROLES)("never appends another role's entries for %s with all grants", role => {
    const auth = useAuthStore(); auth.token = "test-session"; auth.role = role; auth.roles = [role];
    auth.effectivePermissions = allKeys;
    const entries = useMenu().menu.value;
    const actual = entries.flatMap(item => "items" in item ? item.items.map(child => child.path) : [item.path]);
    expect(actual).toEqual(roleMenuPaths(role));
    expect(entries.some(item => item.title === "已授权功能")).toBe(false);
    expect(actual).toContain(auth.resolveDefaultRoute());
  });
  it("extra chat permission does not create an algorithm engineer chat entry or landing page", () => {
    const auth = useAuthStore(); auth.token = "session"; auth.role = "algorithm_engineer"; auth.roles = ["algorithm_engineer"];
    auth.effectivePermissions = ["chat", "model_config_read"];
    const entries = useMenu().menu.value;
    const paths = entries.flatMap(item => "items" in item ? item.items.map(child => child.path) : [item.path]);
    expect(paths).not.toContain("/app/chat");
    expect(auth.resolveDefaultRoute()).toBe("/governance/admin/models");
  });
  it('falls back to chat when an expert does not have business-workbench permissions', () => {
    const auth = useAuthStore(); auth.token = 'session'; auth.role = 'expert'; auth.roles = ['expert'];
    auth.effectivePermissions = ['chat'];
    expect(auth.resolveDefaultRoute()).toBe('/app/chat');
    expect(useMenu().menu.value.some(item => item.title === '质监工作台')).toBe(false);
  });
});
