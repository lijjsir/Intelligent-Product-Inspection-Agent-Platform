<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth.store";
import { useUserStore } from "@/stores/user.store";
import { usePagination } from "@/composables/usePagination";
import { usePermission } from "@/composables/usePermission";
import {
  ROLE_ADMIN,
  ROLE_APP_DEVELOPER,
  ROLE_ALGORITHM_ENGINEER,
  ROLE_USER,
} from "@/constants/roles";
import type { User } from "@/types/user.types";

const router = useRouter();
const store = useUserStore();
const authStore = useAuthStore();
const { hasRole } = usePermission();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const canManageUsers = computed(() => hasRole(ROLE_ADMIN));

const filters = reactive({
  keyword: "",
  role: "",
  status: "",
});

const showCreateDialog = ref(false);
const showResetPasswordDialog = ref(false);
const creating = ref(false);
const resettingPassword = ref(false);
const createFormRef = ref<FormInstance>();
const resetPasswordFormRef = ref<FormInstance>();
const createForm = reactive({
  username: "",
  email: "",
  password: "",
  role: ROLE_USER,
});
const resetPasswordForm = reactive({
  userId: "",
  username: "",
  password: "",
});

const roleMeta: Record<string, { label: string; tag: "danger" | "success" | "warning" | "info" }> = {
  [ROLE_ADMIN]: { label: "管理员", tag: "danger" },
  [ROLE_USER]: { label: "普通用户", tag: "info" },
  [ROLE_ALGORITHM_ENGINEER]: { label: "算法工程师", tag: "success" },
  [ROLE_APP_DEVELOPER]: { label: "应用开发者", tag: "warning" },
};

const roleOptions = computed(() =>
  store.assignableRoles.map((role) => ({
    value: role,
    label: roleMeta[role]?.label ?? role,
  })),
);

const createRules: FormRules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  email: [{ required: true, type: "email", message: "请输入有效邮箱", trigger: "blur" }],
  password: [{ required: true, min: 6, message: "密码不少于 6 位", trigger: "blur" }],
  role: [{ required: true, message: "请选择角色", trigger: "change" }],
};

const resetPasswordRules: FormRules = {
  password: [{ required: true, min: 6, message: "密码不少于 6 位", trigger: "blur" }],
};

onMounted(async () => {
  if (!canManageUsers.value) {
    ElMessage.error("权限不足，无法访问用户管理");
    return;
  }
  await Promise.all([store.fetchAssignableRoles(), fetchData()]);
});

async function fetchData() {
  await store.fetchUsers({
    page: page.value,
    size: pageSize.value,
    keyword: filters.keyword.trim() || undefined,
    role: filters.role || undefined,
    is_active: filters.status ? filters.status === "active" : undefined,
  });
  total.value = store.total;
}

function handleSearch() {
  resetPage();
  fetchData();
}

function handleResetFilters() {
  filters.keyword = "";
  filters.role = "";
  filters.status = "";
  resetPage();
  fetchData();
}

function handleSizeChange(size: number) {
  onSizeChange(size);
  fetchData();
}

function handleCurrentChange(currentPage: number) {
  onPageChange(currentPage);
  fetchData();
}

function openCreateDialog() {
  createForm.username = "";
  createForm.email = "";
  createForm.password = "";
  createForm.role = roleOptions.value[0]?.value ?? ROLE_USER;
  showCreateDialog.value = true;
}

async function handleSubmitCreate() {
  if (!createFormRef.value) return;

  const valid = await createFormRef.value.validate().catch(() => false);
  if (!valid) return;

  creating.value = true;
  try {
    await store.createUser({ ...createForm });
    ElMessage.success(`用户 ${createForm.username} 已创建`);
    showCreateDialog.value = false;
    await fetchData();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "创建失败");
  } finally {
    creating.value = false;
  }
}

async function handleRoleChange(row: User, role: string) {
  try {
    await store.updateRole(row.id, role);
    ElMessage.success(`已更新 ${row.username} 的角色`);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "角色更新失败");
    await fetchData();
  }
}

async function handleStatusChange(row: User, nextValue: boolean) {
  try {
    await store.updateStatus(row.id, nextValue);
    ElMessage.success(`已更新 ${row.username} 的启停用状态`);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "状态更新失败");
    await fetchData();
  }
}

function openResetPasswordDialog(row: User) {
  resetPasswordForm.userId = row.id;
  resetPasswordForm.username = row.username;
  resetPasswordForm.password = "";
  showResetPasswordDialog.value = true;
}

async function handleResetPassword() {
  if (!resetPasswordFormRef.value) return;

  const valid = await resetPasswordFormRef.value.validate().catch(() => false);
  if (!valid) return;

  resettingPassword.value = true;
  try {
    await store.resetPassword(resetPasswordForm.userId, resetPasswordForm.password);
    ElMessage.success(`已重置 ${resetPasswordForm.username} 的密码`);
    showResetPasswordDialog.value = false;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "密码重置失败");
  } finally {
    resettingPassword.value = false;
  }
}

function goProfile() {
  router.push("/app/profile");
}

function formatDateTime(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function getRoleLabel(role: string) {
  return roleMeta[role]?.label ?? role;
}

function getRoleTag(role: string) {
  return roleMeta[role]?.tag ?? "info";
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold text-zinc-900">用户管理</h2>
        <p class="mt-2 text-sm text-zinc-500">补齐筛选、密码重置和角色策略接口化后的用户治理闭环。</p>
      </div>
      <div class="flex gap-3">
        <el-button size="small" @click="goProfile">个人资料</el-button>
        <el-button type="primary" size="small" @click="openCreateDialog" v-if="canManageUsers">新建用户</el-button>
      </div>
    </div>

    <div class="card-surface p-4" v-if="canManageUsers">
      <el-form inline class="flex flex-wrap gap-x-4 gap-y-2 items-end">
        <el-form-item label="关键词">
          <el-input
            v-model="filters.keyword"
            placeholder="用户名或邮箱"
            clearable
            class="!w-[220px]"
            size="small"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="filters.role" placeholder="全部" clearable class="!w-[180px]" size="small">
            <el-option
              v-for="option in roleOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部" clearable class="!w-[140px]" size="small">
            <el-option label="启用中" value="active" />
            <el-option label="已停用" value="inactive" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="small" @click="handleSearch">查询</el-button>
          <el-button size="small" @click="handleResetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="card-surface" v-if="canManageUsers">
      <el-table :data="store.items" v-loading="store.loading" size="small" class="list-table">
        <el-table-column prop="username" label="用户名" min-width="160" />
        <el-table-column prop="email" label="邮箱" min-width="220" show-overflow-tooltip />
        <el-table-column label="角色" width="180">
          <template #default="{ row }">
            <el-select
              :model-value="row.role"
              @change="(value) => handleRoleChange(row, value)"
              :disabled="row.id === authStore.userId"
              size="small"
              class="!w-[148px]"
            >
              <el-option
                v-for="option in roleOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              @change="(value) => handleStatusChange(row, value)"
              :disabled="row.id === authStore.userId"
              size="small"
            />
          </template>
        </el-table-column>
        <el-table-column label="当前标识" width="150">
          <template #default="{ row }">
            <el-tag :type="getRoleTag(row.role)" effect="plain" size="small">{{ getRoleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openResetPasswordDialog(row)" :disabled="row.id === authStore.userId">
              重置密码
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="flex justify-end p-4">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          size="small"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <div v-else class="grid place-items-center min-h-[320px] bg-white rounded-2xl">
      <el-empty description="当前账号没有用户管理权限" />
    </div>

    <el-dialog v-model="showCreateDialog" title="新建用户" width="480px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="88px" size="small">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="例如 inspector_wang" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="createForm.email" placeholder="example@company.com" />
        </el-form-item>
        <el-form-item label="初始密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="不少于 6 位" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="createForm.role">
            <el-radio v-for="option in roleOptions" :key="option.value" :label="option.value">
              {{ option.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="handleSubmitCreate">创建</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="showResetPasswordDialog" title="重置密码" width="420px" destroy-on-close>
      <el-form ref="resetPasswordFormRef" :model="resetPasswordForm" :rules="resetPasswordRules" label-width="88px" size="small">
        <el-form-item label="用户">
          <el-input :model-value="resetPasswordForm.username" disabled />
        </el-form-item>
        <el-form-item label="新密码" prop="password">
          <el-input v-model="resetPasswordForm.password" type="password" show-password placeholder="不少于 6 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <el-button @click="showResetPasswordDialog = false">取消</el-button>
          <el-button type="primary" :loading="resettingPassword" @click="handleResetPassword">确认重置</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.list-table :deep(.el-table__header th) {
  @apply text-zinc-500 font-medium text-[13px] bg-zinc-50;
}
.list-table :deep(.el-table__body tr:hover > td) {
  @apply bg-zinc-50;
}
</style>
