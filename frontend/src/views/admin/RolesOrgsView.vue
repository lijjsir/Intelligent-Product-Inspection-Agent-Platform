<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { rolesOrgsApi } from "@/api/roles-orgs.api";
import { userApi } from "@/api/user.api";
import { ROLE_ADMIN } from "@/constants/roles";
import { useAuthStore } from "@/stores/auth.store";
import type {
  Organization,
  OrganizationCreatePayload,
  OrganizationUpdatePayload,
  OrganizationUserItem,
  RoleItem,
  RolesPermissionMatrix,
} from "@/types/governance.types";
import type { User } from "@/types/user.types";

const auth = useAuthStore();

const activeTab = ref("roles");
const roles = ref<RoleItem[]>([]);
const permissionMatrix = ref<RolesPermissionMatrix | null>(null);
const organizations = ref<Organization[]>([]);
const loading = ref(false);
const orgDrawerOpen = ref(false);
const userDrawerOpen = ref(false);
const submitting = ref(false);
const assigning = ref(false);
const editingOrgId = ref("");
const selectedOrg = ref<Organization | null>(null);
const organizationUsers = ref<OrganizationUserItem[]>([]);
const allUsers = ref<User[]>([]);
const selectedUserIds = ref<string[]>([]);
const settingsText = ref("{}");

const form = reactive<OrganizationCreatePayload & { is_active: boolean }>({
  name: "",
  slug: "",
  plan: "standard",
  settings: {},
  is_active: true,
});

const roleLabelMap = computed(() =>
  Object.fromEntries(roles.value.map((item) => [item.key, item.label])),
);
const roleColumns = computed(() => roles.value.map((item) => item.key));
const resourceRows = computed(() => {
  const matrix = permissionMatrix.value;
  if (!matrix) return [];
  return matrix.resources.map((resource) => ({
    resource,
    roleStates: Object.fromEntries(roleColumns.value.map((role) => [role, matrix.matrix[role]?.includes(resource) ?? false])),
  }));
});
const availableUsers = computed(() => {
  if (!selectedOrg.value) return [];
  const assignedIds = new Set(organizationUsers.value.map((item) => item.id));
  return allUsers.value.filter((user) => !assignedIds.has(user.id) || user.org_id === selectedOrg.value?.id);
});
const isAdmin = computed(() => auth.primaryRole === ROLE_ADMIN);

onMounted(async () => {
  if (!isAdmin.value) return;
  await Promise.all([fetchRolesData(), fetchOrganizations()]);
});

async function fetchRolesData() {
  const [rolesResp, matrixResp] = await Promise.all([
    rolesOrgsApi.listRoles(),
    rolesOrgsApi.getPermissionsMatrix(),
  ]);
  roles.value = rolesResp.data.data;
  permissionMatrix.value = matrixResp.data.data;
}

async function fetchOrganizations() {
  loading.value = true;
  try {
    const { data } = await rolesOrgsApi.listOrganizations();
    organizations.value = data.data;
  } finally {
    loading.value = false;
  }
}

function resetForm() {
  editingOrgId.value = "";
  form.name = "";
  form.slug = "";
  form.plan = "standard";
  form.settings = {};
  form.is_active = true;
  settingsText.value = "{}";
}

function openCreateOrg() {
  resetForm();
  orgDrawerOpen.value = true;
}

function openEditOrg(org: Organization) {
  editingOrgId.value = org.id;
  form.name = org.name;
  form.slug = org.slug;
  form.plan = org.plan;
  form.settings = org.settings ?? {};
  form.is_active = org.is_active;
  settingsText.value = formatSettings(org.settings);
  orgDrawerOpen.value = true;
}

async function submitOrg() {
  submitting.value = true;
  try {
    const parsedSettings = settingsText.value.trim() ? JSON.parse(settingsText.value) : {};
    const basePayload = {
      name: form.name.trim(),
      slug: form.slug.trim(),
      plan: form.plan.trim(),
      settings: parsedSettings,
    };
    if (editingOrgId.value) {
      const payload: OrganizationUpdatePayload = {
        ...basePayload,
        is_active: form.is_active,
      };
      await rolesOrgsApi.updateOrganization(editingOrgId.value, payload);
      ElMessage.success("组织已更新");
    } else {
      const payload: OrganizationCreatePayload = basePayload;
      await rolesOrgsApi.createOrganization(payload);
      ElMessage.success("组织已创建");
    }
    orgDrawerOpen.value = false;
    await fetchOrganizations();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "组织保存失败");
  } finally {
    submitting.value = false;
  }
}

async function removeOrg(org: Organization) {
  await ElMessageBox.confirm(`确认删除组织 ${org.name} 吗？`, "删除组织", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  await rolesOrgsApi.deleteOrganization(org.id);
  ElMessage.success("组织已删除");
  await fetchOrganizations();
}

async function openUsersDrawer(org: Organization) {
  selectedOrg.value = org;
  userDrawerOpen.value = true;
  assigning.value = true;
  try {
    const [orgUsersResp, usersResp] = await Promise.all([
      rolesOrgsApi.getOrganizationUsers(org.id),
      userApi.list({ page: 1, size: 200 }),
    ]);
    organizationUsers.value = orgUsersResp.data.data.users;
    allUsers.value = usersResp.data.data.items as User[];
    selectedUserIds.value = [];
  } finally {
    assigning.value = false;
  }
}

async function assignSelectedUsers() {
  if (!selectedOrg.value || !selectedUserIds.value.length) {
    ElMessage.warning("请先选择用户");
    return;
  }
  assigning.value = true;
  try {
    await rolesOrgsApi.assignUsersToOrganization(selectedOrg.value.id, {
      user_ids: selectedUserIds.value,
      action: "assign",
    });
    ElMessage.success("用户分配成功");
    await openUsersDrawer(selectedOrg.value);
  } finally {
    assigning.value = false;
  }
}

async function removeUserFromOrg(user: OrganizationUserItem) {
  if (!selectedOrg.value) return;
  assigning.value = true;
  try {
    await rolesOrgsApi.assignUsersToOrganization(selectedOrg.value.id, {
      user_ids: [user.id],
      action: "remove",
    });
    ElMessage.success("用户已移出组织");
    await openUsersDrawer(selectedOrg.value);
  } finally {
    assigning.value = false;
  }
}

function formatSettings(value: Record<string, unknown> | null | undefined) {
  return value ? JSON.stringify(value) : "{}";
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold text-zinc-900">权限与组织</h2>
        <p class="mt-2 text-sm text-zinc-500">集中查看固定角色权限矩阵，并完成组织管理和组织内用户分配。</p>
      </div>
      <el-button type="primary" size="small" @click="openCreateOrg">新建组织</el-button>
    </div>

    <div class="card-surface p-4">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="角色总览" name="roles">
          <el-table :data="resourceRows" size="small" class="list-table">
            <el-table-column prop="resource" label="资源" min-width="180" />
            <el-table-column
              v-for="role in roleColumns"
              :key="role"
              :label="roleLabelMap[role] || role"
              min-width="120"
              align="center"
            >
              <template #default="{ row }">
                <el-tag :type="row.roleStates[role] ? 'success' : 'info'" effect="light">
                  {{ row.roleStates[role] ? "有权限" : "无权限" }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="组织管理" name="orgs">
          <el-table :data="organizations" v-loading="loading" size="small" class="list-table">
            <el-table-column prop="name" label="名称" min-width="180" />
            <el-table-column prop="slug" label="Slug" min-width="140" />
            <el-table-column prop="plan" label="套餐" width="120" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" effect="light">
                  {{ row.is_active ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="user_count" label="用户数" width="100" />
            <el-table-column label="配置" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ formatSettings(row.settings) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="260" fixed="right">
              <template #default="{ row }">
                <div class="flex gap-2">
                  <el-button size="small" @click="openEditOrg(row)">编辑</el-button>
                  <el-button size="small" @click="openUsersDrawer(row)">用户分配</el-button>
                  <el-button size="small" type="danger" plain @click="removeOrg(row)">删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-drawer v-model="orgDrawerOpen" :title="editingOrgId ? '编辑组织' : '新建组织'" size="420px">
      <div class="flex flex-col gap-4">
        <el-form label-position="top">
          <el-form-item label="组织名称">
            <el-input v-model="form.name" placeholder="请输入组织名称" />
          </el-form-item>
          <el-form-item label="Slug">
            <el-input v-model="form.slug" placeholder="请输入 slug" />
          </el-form-item>
          <el-form-item label="套餐">
            <el-input v-model="form.plan" placeholder="standard" />
          </el-form-item>
          <el-form-item label="设置 JSON">
            <el-input
              v-model="settingsText"
              type="textarea"
              :rows="6"
            />
          </el-form-item>
          <el-form-item label="状态">
            <el-switch v-model="form.is_active" />
          </el-form-item>
        </el-form>
        <div class="flex justify-end gap-3">
          <el-button @click="orgDrawerOpen = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitOrg">保存</el-button>
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="userDrawerOpen" :title="selectedOrg ? `${selectedOrg.name} · 用户分配` : '用户分配'" size="560px">
      <div class="flex flex-col gap-4" v-loading="assigning">
        <div class="card-surface p-4">
          <div class="flex flex-wrap gap-3 items-end">
            <div class="min-w-[240px] flex-1">
              <div class="mb-2 text-sm text-zinc-500">添加用户到组织</div>
              <el-select v-model="selectedUserIds" multiple collapse-tags collapse-tags-tooltip class="w-full">
                <el-option
                  v-for="user in availableUsers"
                  :key="user.id"
                  :label="`${user.username} (${user.role})`"
                  :value="user.id"
                />
              </el-select>
            </div>
            <el-button type="primary" @click="assignSelectedUsers">批量分配</el-button>
          </div>
        </div>

        <el-table :data="organizationUsers" size="small" class="list-table">
          <el-table-column prop="username" label="用户名" min-width="180" />
          <el-table-column prop="role" label="角色" width="160" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" effect="light">
                {{ row.is_active ? "启用" : "停用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" type="danger" plain disabled @click="removeUserFromOrg(row)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <p class="text-xs text-zinc-400">当前用户组织字段仍为必填，移除组织会产生无归属用户，因此本轮暂不开放移除。</p>
      </div>
    </el-drawer>
  </div>
</template>
