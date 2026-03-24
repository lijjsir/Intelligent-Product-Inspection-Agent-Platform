import { defineStore } from "pinia";
import { ref } from "vue";
import { userApi } from "@/api/user.api";
import type { User, UserCreate, UserListQuery, UserProfileUpdate } from "@/types/user.types";

export const useUserStore = defineStore("user", () => {
  const items = ref<User[]>([]);
  const current = ref<User | null>(null);
  const total = ref(0);
  const loading = ref(false);
  const assignableRoles = ref<string[]>([]);

  async function fetchUsers(query: UserListQuery) {
    loading.value = true;
    try {
      const { data } = await userApi.list(query);
      items.value = data.data.items;
      total.value = data.data.total;
    } finally {
      loading.value = false;
    }
  }

  async function createUser(payload: UserCreate) {
    const { data } = await userApi.create(payload);
    items.value.unshift(data.data);
    total.value++;
    return data.data;
  }

  async function fetchCurrentUser() {
    const { data } = await userApi.getMe();
    current.value = data.data;
    return data.data;
  }

  async function updateCurrentUser(payload: UserProfileUpdate) {
    const { data } = await userApi.updateMe(payload);
    current.value = data.data;
    return data.data;
  }

  async function fetchAssignableRoles() {
    const { data } = await userApi.getAssignableRoles();
    assignableRoles.value = data.data;
    return data.data;
  }

  async function updateRole(id: string, role: string) {
    const { data } = await userApi.updateRole(id, { role });
    const idx = items.value.findIndex(u => u.id === id);
    if (idx !== -1) items.value[idx] = data.data;
    if (current.value?.id === id) current.value = data.data;
  }

  async function updateStatus(id: string, is_active: boolean) {
    const { data } = await userApi.updateStatus(id, { is_active });
    const idx = items.value.findIndex(u => u.id === id);
    if (idx !== -1) items.value[idx] = data.data;
    if (current.value?.id === id) current.value = data.data;
  }

  async function resetPassword(id: string, password: string) {
    const { data } = await userApi.resetPassword(id, { password });
    const idx = items.value.findIndex(u => u.id === id);
    if (idx !== -1) items.value[idx] = data.data;
    if (current.value?.id === id) current.value = data.data;
    return data.data;
  }

  return {
    items,
    current,
    total,
    loading,
    assignableRoles,
    fetchUsers,
    createUser,
    fetchCurrentUser,
    updateCurrentUser,
    fetchAssignableRoles,
    updateRole,
    updateStatus,
    resetPassword,
  };
});
