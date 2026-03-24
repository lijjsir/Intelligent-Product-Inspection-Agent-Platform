<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { useUserStore } from "@/stores/user.store";
import { useAuthStore } from "@/stores/auth.store";
import { usePermission } from "@/composables/usePermission";
import { usePagination } from "@/composables/usePagination";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import {
  ROLE_AI_QUALITY,
  ROLE_ANALYST,
  ROLE_INSPECTOR,
  ROLE_ORG_ADMIN,
  ROLE_PLATFORM_ADMIN,
  ROLE_SUPER_ADMIN,
  ROLE_VIEWER,
} from "@/constants/roles";

const store = useUserStore();
const authStore = useAuthStore();
const { hasRole } = usePermission();
const { page, pageSize, total, onPageChange, onSizeChange } = usePagination();

const showCreateDialog = ref(false);
const creating = ref(false);
const formRef = ref<FormInstance>();
const createForm = ref({ username: "", email: "", password: "", role: "inspector" });

const assignableRoles = computed(() => {
  if (authStore.role === ROLE_SUPER_ADMIN) {
    return [
      { label: "超级管理员", value: ROLE_SUPER_ADMIN },
      { label: "机构管理", value: ROLE_ORG_ADMIN },
      { label: "质检员", value: ROLE_INSPECTOR },
      { label: "只读访客", value: ROLE_VIEWER },
      { label: "分析员", value: ROLE_ANALYST },
      { label: "平台管理员", value: ROLE_PLATFORM_ADMIN },
      { label: "AI 质量专员", value: ROLE_AI_QUALITY },
    ];
  }
  return [
    { label: "机构管理", value: ROLE_ORG_ADMIN },
    { label: "质检员", value: ROLE_INSPECTOR },
    { label: "只读访客", value: ROLE_VIEWER },
    { label: "分析员", value: ROLE_ANALYST },
    { label: "AI 质量专员", value: ROLE_AI_QUALITY },
  ];
});

const rules: FormRules = {
  username: [{ required: true, message: "必须要填写用户名", trigger: "blur" }],
  email: [{ required: true, type: "email", message: "邮箱格式错误", trigger: "blur" }],
  password: [{ required: true, min: 6, message: "密码须不少于 6 字符", trigger: "blur" }]
};

onMounted(() => {
  if (!hasRole(["super_admin", "org_admin"])) {
    ElMessage.error("权限不足，无法管理同租户用户");
    return;
  }
  fetchData();
});

async function fetchData() {
  await store.fetchUsers({ page: page.value, size: pageSize.value });
  total.value = store.total;
}

function handleSizeChange(val: number) {
  onSizeChange(val);
  fetchData();
}

function handleCurrentChange(val: number) {
  onPageChange(val);
  fetchData();
}

async function handleStatusChange(row: any) {
  try {
    await store.updateStatus(row.id, row.is_active);
    ElMessage.success(`用户 ${row.username} 状态流转成功`);
  } catch (e) {
    row.is_active = !row.is_active; // revert
    ElMessage.error("状态切换阻断");
  }
}

async function handleRoleChange(row: any, newRole: string) {
  try {
    await store.updateRole(row.id, newRole);
    ElMessage.success("权限组刷新完成");
  } catch (e) {
    ElMessage.error("未下发权限修补");
  }
}

async function handleSubmitCreate() {
  if (!formRef.value) return;
  await formRef.value.validate(async valid => {
    if (!valid) return;
    creating.value = true;
    try {
      await store.createUser({
        username: createForm.value.username,
        email: createForm.value.email,
        password: createForm.value.password,
        role: createForm.value.role
      });
      ElMessage.success(`全新员工 ${createForm.value.username} 报建下发！`);
      showCreateDialog.value = false;
      fetchData();
    } catch (e: any) {
    } finally {
      creating.value = false;
    }
  });
}

function getRoleTag(role: string) {
  const map: Record<string, "danger" | "success" | "warning" | "info"> = {
    super_admin: "danger",
    org_admin: "success",
    inspector: "warning",
    viewer: "info",
    analyst: "warning",
    platform_admin: "danger",
    ai_quality: "success",
  };
  return map[role] || "info";
}
</script>

<template>
  <div class="page-container">
    <div class="header">
      <div>
        <h2 class="title">身份授权与全周期雇员池归档</h2>
        <p class="subtitle">仅限 `ORG_ADMIN` 管理该机构下沉人员权限与活动态</p>
      </div>
      <el-button type="primary" @click="showCreateDialog = true" v-if="hasRole(['super_admin', 'org_admin'])">
        + 开设人员条线槽位
      </el-button>
    </div>

    <!-- Table -->
    <el-card shadow="never" class="table-card" v-if="hasRole(['super_admin', 'org_admin'])">
      <el-table :data="store.items" v-loading="store.loading" border stripe style="width: 100%">
        <el-table-column prop="id" label="聚合 ID/UUID" width="280" show-overflow-tooltip />
        <el-table-column prop="username" label="注册句柄 (Username)" width="150" />
        <el-table-column prop="email" label="密令寻回 (Email)" min-width="180" />
        
        <el-table-column label="组织权限组 (Role)" width="160">
          <template #default="{ row }">
            <el-select 
              :model-value="row.role" 
              @change="(v) => handleRoleChange(row, v)"
              :disabled="row.id === authStore.userId"
              size="small"
              style="width: 120px"
            >
              <el-option
                v-for="option in assignableRoles"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="系统级活动封锁 (Active)" width="120" align="center">
          <template #default="{ row }">
            <el-switch 
              v-model="row.is_active" 
              @change="() => handleStatusChange(row)" 
              :disabled="row.id === authStore.userId" 
            />
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
      <el-empty description="无法触达管理组织层级 (非管理员)" />
    </div>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreateDialog" title="颁发准入与开户" width="450px" destroy-on-close>
      <el-form ref="formRef" :model="createForm" :rules="rules" label-width="80px">
        <el-form-item label="登入名" prop="username">
          <el-input v-model="createForm.username" placeholder="如 inspector_wang" />
        </el-form-item>
        <el-form-item label="主验邮箱" prop="email">
          <el-input v-model="createForm.email" placeholder="工作对接邮箱" />
        </el-form-item>
        <el-form-item label="密令锁" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="不小于6位长度" />
        </el-form-item>
        <el-form-item label="权限挂载">
          <el-radio-group v-model="createForm.role">
            <el-radio
              v-for="option in assignableRoles"
              :key="option.value"
              :label="option.value"
            >
              {{ option.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showCreateDialog = false">回退终端</el-button>
          <el-button type="primary" :loading="creating" @click="handleSubmitCreate">激活人员</el-button>
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
  margin-bottom: 24px;
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

.mt-4 {
  margin-top: 16px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
}
</style>
