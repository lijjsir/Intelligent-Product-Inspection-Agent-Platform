<template>
  <div class="auth-form-card auth-login-card w-full">
    <div class="auth-login-heading">
      <h2 class="text-2xl font-bold text-zinc-900">欢迎回来</h2>
      <p class="mt-2 text-sm text-zinc-500">登录 PIAP 智能检测平台</p>
    </div>

    <form class="auth-login-form flex flex-col" @submit.prevent="submit">
      <div class="flex flex-col gap-1.5">
        <label for="login-org" class="text-[13px] font-medium text-zinc-600">组织 ID / slug</label>
        <el-input id="login-org" v-model="orgId" name="organization" autocomplete="section-org organization" placeholder="组织 ID / slug" size="large" clearable>
          <template #prefix><el-icon><OfficeBuilding /></el-icon></template>
        </el-input>
      </div>

      <div class="flex flex-col gap-1.5">
        <label for="login-username" class="text-[13px] font-medium text-zinc-600">账号</label>
        <el-input id="login-username" v-model="username" name="username" autocomplete="section-login username" placeholder="请输入账号" size="large" clearable>
          <template #prefix><el-icon><User /></el-icon></template>
        </el-input>
      </div>

      <div class="flex flex-col gap-1.5">
        <label for="login-password" class="text-[13px] font-medium text-zinc-600">密码</label>
        <el-input
          id="login-password"
          v-model="password"
          name="password"
          autocomplete="section-login current-password"
          type="password"
          placeholder="请输入密码"
          size="large"
          show-password
        >
          <template #prefix><el-icon><Lock /></el-icon></template>
        </el-input>
      </div>

      <div class="auth-login-options">
        <el-checkbox v-model="rememberMe">记住我</el-checkbox>
        <button type="button" class="auth-link" @click="showForgotPassword">忘记密码？</button>
      </div>

      <el-button
        type="primary"
        size="large"
        native-type="submit"
        :loading="loading"
        class="!w-full auth-submit"
      >
        {{ loading ? "登录中..." : "登录" }} <span class="auth-submit-arrow">→</span>
      </el-button>
    </form>

    <div class="auth-register-divider"><span>还没有账号？</span></div>
    <RouterLink to="/register" class="auth-register-button">注册账号</RouterLink>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Lock, OfficeBuilding, User } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth.store";
import { useRuntimeContext } from "@/composables/useRuntimeContext";

const router = useRouter();
const auth = useAuthStore();
const { context: runtimeContext } = useRuntimeContext();

const orgId = ref("cqupt");
const username = ref("");
const password = ref("");
const loading = ref(false);
const rememberMe = ref(true);

onMounted(() => {
  const savedOrg = window.localStorage.getItem("piap_login_org");
  orgId.value = savedOrg || runtimeContext.value?.organization_slug || "cqupt";
  username.value = window.localStorage.getItem("piap_login_username") || "";
  rememberMe.value = Boolean(savedOrg || username.value);
});
watch(runtimeContext, (value) => {
  if (value?.execution_mode === "demo" && !window.localStorage.getItem("piap_login_org") && orgId.value === "cqupt")
    orgId.value = value.organization_slug || "cqupt";
});

const showForgotPassword = () => {
  ElMessage.info("请联系组织管理员重置密码。");
};

const submit = async () => {
  if (loading.value) return;
  if (!orgId.value || !username.value || !password.value) {
    return;
  }
  loading.value = true;
  try {
    await auth.login({
      org_id: orgId.value,
      username: username.value,
      password: password.value,
    });
    if (rememberMe.value) {
      window.localStorage.setItem("piap_login_org", orgId.value);
      window.localStorage.setItem("piap_login_username", username.value);
    } else {
      window.localStorage.removeItem("piap_login_org");
      window.localStorage.removeItem("piap_login_username");
    }
    await router.push(auth.resolveDefaultRoute());
  } catch (error) {
    console.error("登录失败:", error);
  } finally {
    loading.value = false;
  }
};
</script>
