<template>
  <div class="w-full max-w-[360px]">
    <div class="mb-8">
      <h2 class="text-2xl font-bold text-zinc-900">欢迎回来</h2>
      <p class="mt-2 text-sm text-zinc-500">请输入组织标识和账号密码进行登录</p>
    </div>

    <form class="flex flex-col gap-5" @submit.prevent="submit">
      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">组织 ID / slug</label>
        <el-input
          v-model="orgId"
          placeholder="admin 或组织 UUID"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">账号</label>
        <el-input
          v-model="username"
          placeholder="admin"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">密码</label>
        <el-input
          v-model="password"
          type="password"
          placeholder="请输入密码"
          size="large"
          show-password
          @keydown.enter="submit"
        />
      </div>

      <el-button
        type="primary"
        size="large"
        native-type="submit"
        :loading="loading"
        class="!w-full !mt-2"
        @click="submit"
      >
        {{ loading ? "登录中..." : "登录" }}
      </el-button>
    </form>

    <p class="mt-6 text-center text-[13px] text-zinc-400">
      还没有账号？
      <RouterLink to="/register" class="text-zinc-900 font-medium hover:underline">创建组织</RouterLink>
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";

const router = useRouter();
const auth = useAuthStore();

const orgId = ref("");
const username = ref("");
const password = ref("");
const loading = ref(false);

const submit = async () => {
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
    await router.push(auth.resolveDefaultRoute());
  } catch (error) {
    console.error("登录失败:", error);
  } finally {
    loading.value = false;
  }
};
</script>
