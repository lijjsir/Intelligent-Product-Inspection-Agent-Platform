import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { useAuthStore } from "@/stores/auth.store";

export const useNavigationStore = defineStore("navigation", () => {
  const auth = useAuthStore();
  const expandedGroups = ref<string[]>([]);
  const collapsedGroups = ref<string[]>([]);

  // Keep navigation choices across layout remounts, but start fresh at login.
  watch(
    () => [auth.isAuthed, auth.orgId, auth.userId, auth.primaryRole],
    () => {
      expandedGroups.value = [];
      collapsedGroups.value = [];
    },
    { flush: "sync" },
  );

  function revealGroups(titles: string[]) {
    expandedGroups.value = Array.from(
      new Set([
        ...expandedGroups.value,
        ...titles.filter((title) => !collapsedGroups.value.includes(title)),
      ]),
    );
  }

  function toggleGroup(title: string) {
    if (expandedGroups.value.includes(title)) {
      expandedGroups.value = expandedGroups.value.filter((item) => item !== title);
      collapsedGroups.value = Array.from(new Set([...collapsedGroups.value, title]));
      return false;
    }
    collapsedGroups.value = collapsedGroups.value.filter((item) => item !== title);
    expandedGroups.value = [...expandedGroups.value, title];
    return true;
  }

  return { expandedGroups, revealGroups, toggleGroup };
});
