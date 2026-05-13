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
  <div v-loading="loading" class="flex flex-col gap-5">
    <div>
      <h2 class="text-2xl font-bold text-zinc-900">个人资料</h2>
      <p class="mt-2 text-sm text-zinc-500">维护当前登录账号的基础信息和密码。</p>
    </div>

    <div class="grid grid-cols-2 gap-4 max-md:grid-cols-1">
      <div class="card-surface col-span-2">
        <div class="px-5 py-3 border-b border-zinc-100 text-sm font-semibold text-zinc-900">账户信息</div>
        <div class="p-5">
          <el-descriptions :column="1" border v-if="store.current" size="small">
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
        </div>
      </div>

      <div class="card-surface">
        <div class="px-5 py-3 border-b border-zinc-100 text-sm font-semibold text-zinc-900">基础资料</div>
        <div class="p-5">
          <el-form ref="profileFormRef" :model="profileForm" :rules="profileRules" label-width="88px" size="small">
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
        </div>
      </div>

      <div class="card-surface">
        <div class="px-5 py-3 border-b border-zinc-100 text-sm font-semibold text-zinc-900">修改密码</div>
        <div class="p-5">
          <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="88px" size="small">
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
        </div>
      </div>
    </div>
  </div>
</template>
