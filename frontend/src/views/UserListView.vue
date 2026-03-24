<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth.store";
import { useUserStore } from "@/stores/user.store";
import { usePagination } from "@/composables/usePagination";
import { usePermission } from "@/composables/usePermission";
import {
  ROLE_AI_QUALITY,
  ROLE_ANALYST,
  ROLE_INSPECTOR,
  ROLE_ORG_ADMIN,
  ROLE_PLATFORM_ADMIN,
  ROLE_SUPER_ADMIN,
  ROLE_VIEWER,
} from "@/constants/roles";
import type { User } from "@/types/user.types";

const router = useRouter();
const store = useUserStore();
const authStore = useAuthStore();
const { hasRole } = usePermission();
const { page, pageSize, total, onPageChange, onSizeChange, resetPage } = usePagination();

const canManageUsers = computed(() => hasRole([ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN]));

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
  role: ROLE_INSPECTOR,
});
const resetPasswordForm = reactive({
  userId: "",
  username: "",
  password: "",
});

const roleMeta: Record<string, { label: string; tag: "danger" | "success" | "warning" | "info" }> = {
  [ROLE_SUPER_ADMIN]: { label: "超级管理员", tag: "danger" },
  [ROLE_ORG_ADMIN]: { label: "机构管理", tag: "success" },
  [ROLE_INSPECTOR]: { label: "质检员", tag: "warning" },
  [ROLE_VIEWER]: { label: "只读访客", tag: "info" },
  [ROLE_ANALYST]: { label: "分析员", tag: "warning" },
  [ROLE_PLATFORM_ADMIN]: { label: "平台管理员", tag: "danger" },
  [ROLE_AI_QUALITY]: { label: "AI 质量专员", tag: "success" },
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
  createForm.role = roleOptions.value[0]?.value ?? ROLE_INSPECTOR;
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
  router.push("/profile");
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
  <div class="page-container">
    <div class="header">
      <div>
        <h2 class="title">用户管理</h2>
        <p class="subtitle">补齐筛选、密码重置和角色策略接口化后的用户治理闭环。</p>
      </div>
      <div class="actions">
        <el-button @click="goProfile">个人资料</el-button>
        <el-button type="primary" @click="openCreateDialog" v-if="canManageUsers">新建用户</el-button>
      </div>
    </div>

    <el-card class="mb-4" shadow="never" v-if="canManageUsers">
      <el-form inline class="filter-form">
        <el-form-item label="关键词">
          <el-input
            v-model="filters.keyword"
            placeholder="用户名或邮箱"
            clearable
            style="width: 220px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="filters.role" placeholder="全部" clearable style="width: 180px">
            <el-option
              v-for="option in roleOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部" clearable style="width: 140px">
            <el-option label="启用中" value="active" />
            <el-option label="已停用" value="inactive" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleResetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card" v-if="canManageUsers">
      <el-table :data="store.items" v-loading="store.loading" border stripe style="width: 100%">
        <el-table-column prop="username" label="用户名" min-width="160" />
        <el-table-column prop="email" label="邮箱" min-width="220" show-overflow-tooltip />
        <el-table-column label="角色" width="180">
          <template #default="{ row }">
            <el-select
              :model-value="row.role"
              @change="(value) => handleRoleChange(row, value)"
              :disabled="row.id === authStore.userId"
              size="small"
              style="width: 148px"
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
            />
          </template>
        </el-table-column>
        <el-table-column label="当前标识" width="150">
          <template #default="{ row }">
            <el-tag :type="getRoleTag(row.role)" effect="plain">{{ getRoleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openResetPasswordDialog(row)" :disabled="row.id === authStore.userId">
              重置密码
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper mt-4">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <div v-else class="empty-state">
      <el-empty description="当前账号没有用户管理权限" />
    </div>

    <el-dialog v-model="showCreateDialog" title="新建用户" width="480px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="88px">
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
        <span class="dialog-footer">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="handleSubmitCreate">创建</el-button>
        </span>
      </template>
    </el-dialog>

    <el-dialog v-model="showResetPasswordDialog" title="重置密码" width="420px" destroy-on-close>
      <el-form ref="resetPasswordFormRef" :model="resetPasswordForm" :rules="resetPasswordRules" label-width="88px">
        <el-form-item label="用户">
          <el-input :model-value="resetPasswordForm.username" disabled />
        </el-form-item>
        <el-form-item label="新密码" prop="password">
          <el-input v-model="resetPasswordForm.password" type="password" show-password placeholder="不少于 6 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showResetPasswordDialog = false">取消</el-button>
          <el-button type="primary" :loading="resettingPassword" @click="handleResetPassword">确认重置</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background-color: #f3f4f6;
  min-height: 100vh;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
}

.actions {
  display: flex;
  gap: 12px;
}

.title {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #111827;
}

.subtitle {
  margin: 0;
  color: #6b7280;
  font-size: 14px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
}

.mb-4 {
  margin-bottom: 16px;
}

.mt-4 {
  margin-top: 16px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
}

.empty-state {
  display: grid;
  place-items: center;
  min-height: 320px;
  background: #fff;
  border-radius: 16px;
}

@media (max-width: 768px) {
  .header {
    flex-direction: column;
  }

  .actions {
    width: 100%;
  }
}
</style>
