import { computed } from "vue";
import { useAuthStore } from "@/stores/auth.store";
import { permissionsForRoute } from "@/utils/permission-routes";
import { roleMenuFor, type MenuItem, type MenuGroup, type MenuStructure } from "@/utils/role-navigation";
export type { MenuItem, MenuGroup, MenuStructure } from "@/utils/role-navigation";
import { ROLE_ADMIN } from "@/constants/roles";

export function isMenuGroup(entry: MenuItem | MenuGroup): entry is MenuGroup {
  return "items" in entry;
}

export function toggleActiveMenuGroupTitle(activeTitles: string[], title: string) {
  return activeTitles.includes(title)
    ? activeTitles.filter((item) => item !== title)
    : [...activeTitles, title];
}

export function resolveMenuGroupLandingPath(group: MenuGroup) {
  return group.items.find((item) => !item.placeholder)?.path;
}

export function useMenu() {
  const auth = useAuthStore();

  const primaryRole = computed(() => auth.primaryRole || auth.roles[0] || "");

  const showWorkspaceGroups = computed(() => primaryRole.value === ROLE_ADMIN);

  const roleMenu = computed<MenuStructure>(() => roleMenuFor(primaryRole.value));

  const menu = computed<MenuStructure>(() => {
    if (auth.effectivePermissions === null) return roleMenu.value;
    const accessible = (item: MenuItem) => {
      const keys = permissionsForRoute(item.path);
      return !keys || auth.hasPermission(keys);
    };
    const result: MenuStructure = roleMenu.value.flatMap<MenuItem | MenuGroup>((entry) => {
      if (!isMenuGroup(entry)) return accessible(entry) ? [entry] : [];
      const items = entry.items.filter(accessible);
      return items.length ? [{ ...entry, items }] : [];
    });
    return result;
  });

  return { menu, primaryRole, showWorkspaceGroups };
}
