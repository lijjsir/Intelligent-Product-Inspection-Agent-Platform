<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";

import { useUserStore } from "@/stores/user.store";

const store = useUserStore();
const loading = ref(false);
const savingProfile = ref(false);
const changingPassword = ref(false);
const profileFormRef = ref<FormInstance>();
const passwordFormRef = ref<FormInstance>();

const profileForm = reactive({
  username: "",
  email: "",
});

const passwordForm = reactive({
  current_password: "",
  new_password: "",
});

const profileRules: FormRules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  email: [{ required: true, type: "email", message: "请输入有效邮箱", trigger: "blur" }],
};

const passwordRules: FormRules = {
  current_password: [{ required: true, message: "请输入当前密码", trigger: "blur" }],
  new_password: [{ required: true, min: 6, message: "新密码不少于 6 位", trigger: "blur" }],
};

onMounted(() => {
  fetchProfile();
});

async function fetchProfile() {
  loading.value = true;
  try {
    const user = await store.fetchCurrentUser();
    profileForm.username = user.username;
    profileForm.email = user.email;
  } finally {
    loading.value = false;
  }
}

async function handleSaveProfile() {
  if (!profileFormRef.value) return;

  const valid = await profileFormRef.value.validate().catch(() => false);
  if (!valid) return;

  savingProfile.value = true;
  try {
    const user = await store.updateCurrentUser({
      username: profileForm.username,
      email: profileForm.email,
    });
    profileForm.username = user.username;
    profileForm.email = user.email;
    ElMessage.success("个人资料已更新");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "资料更新失败");
  } finally {
    savingProfile.value = false;
  }
}

async function handleChangePassword() {
  if (!passwordFormRef.value) return;

  const valid = await passwordFormRef.value.validate().catch(() => false);
  if (!valid) return;

  changingPassword.value = true;
  try {
    await store.updateCurrentUser({
      current_password: passwordForm.current_password,
      new_password: passwordForm.new_password,
    });
    passwordForm.current_password = "";
    passwordForm.new_password = "";
    ElMessage.success("密码已更新");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.message || "密码更新失败");
  } finally {
    changingPassword.value = false;
  }
}

function formatDateTime(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}
</script>

<template>
  <div class="page-container" v-loading="loading">
    <div class="header">
      <div>
        <h2 class="title">个人资料</h2>
        <p class="subtitle">维护当前登录账号的基础信息和密码。</p>
      </div>
    </div>

    <div class="profile-grid">
      <el-card shadow="never">
        <template #header>
          <div class="card-title">账户信息</div>
        </template>

        <el-descriptions :column="1" border v-if="store.current">
          <el-descriptions-item label="用户 ID">{{ store.current.id }}</el-descriptions-item>
          <el-descriptions-item label="组织 ID">{{ store.current.org_id }}</el-descriptions-item>
          <el-descriptions-item label="角色">{{ store.current.role }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            {{ store.current.is_active ? "启用中" : "已停用" }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatDateTime(store.current.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ formatDateTime(store.current.updated_at) }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-title">基础资料</div>
        </template>

        <el-form ref="profileFormRef" :model="profileForm" :rules="profileRules" label-width="88px">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="profileForm.username" />
          </el-form-item>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="profileForm.email" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="savingProfile" @click="handleSaveProfile">保存资料</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-title">修改密码</div>
        </template>

        <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="88px">
          <el-form-item label="当前密码" prop="current_password">
            <el-input v-model="passwordForm.current_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码" prop="new_password">
            <el-input v-model="passwordForm.new_password" type="password" show-password />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="changingPassword" @click="handleChangePassword">更新密码</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  background-color: #f3f4f6;
  min-height: 100vh;
}

.header {
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

.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.profile-grid > :first-child {
  grid-column: 1 / -1;
}

.card-title {
  font-weight: 600;
  color: #1b3a5c;
}

@media (max-width: 960px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
}
</style>
