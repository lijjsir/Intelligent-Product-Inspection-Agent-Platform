import { defineStore } from "pinia";
import { ref } from "vue";
import { userApi } from "@/api/user.api";
import type { User, UserCreate } from "@/types/user.types";
import type { PageParams } from "@/types/common.types";

export const useUserStore = defineStore("user", () => {
  const items = ref<User[]>([]);
  const total = ref(0);
  const loading = ref(false);

  async function fetchUsers(query: PageParams) {
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

  async function updateRole(id: string, role: string) {
    await userApi.updateRole(id, { role });
    const idx = items.value.findIndex(u => u.id === id);
    if (idx !== -1) items.value[idx].role = role;
  }

  async function updateStatus(id: string, is_active: boolean) {
    await userApi.updateStatus(id, { is_active });
    const idx = items.value.findIndex(u => u.id === id);
    if (idx !== -1) items.value[idx].is_active = is_active;
  }

  return { items, total, loading, fetchUsers, createUser, updateRole, updateStatus };
});
