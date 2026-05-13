<template>
  <div class="w-full max-w-[360px]">
    <div class="mb-8">
      <h2 class="text-2xl font-bold text-zinc-900">创建组织</h2>
      <p class="mt-2 text-sm text-zinc-500">注册后会自动创建组织与管理员账号</p>
    </div>

    <form class="flex flex-col gap-5" @submit.prevent="submit">
      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">组织名称</label>
        <el-input
          v-model="orgName"
          placeholder="PIAP Labs"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">组织标识</label>
        <el-input
          v-model="orgSlug"
          placeholder="piap-labs"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">管理员账号</label>
        <el-input
          v-model="username"
          placeholder="admin"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">管理员邮箱</label>
        <el-input
          v-model="email"
          type="email"
          placeholder="admin@piap.ai"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">管理员密码</label>
        <el-input
          v-model="password"
          type="password"
          placeholder="••••••"
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
        {{ loading ? "创建中..." : "创建并登录" }}
      </el-button>
    </form>

    <p class="mt-6 text-center text-[13px] text-zinc-400">
      已有账号？
      <RouterLink to="/login" class="text-zinc-900 font-medium hover:underline">返回登录</RouterLink>
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";

const router = useRouter();
const auth = useAuthStore();

const orgName = ref("");
const orgSlug = ref("");
const username = ref("");
const email = ref("");
const password = ref("");
const loading = ref(false);

const submit = async () => {
  if (!orgName.value || !orgSlug.value || !username.value || !email.value || !password.value) {
    return;
  }
  loading.value = true;
  try {
    await auth.register({
      org_name: orgName.value,
      org_slug: orgSlug.value,
      username: username.value,
      email: email.value,
      password: password.value,
    });
    router.push(auth.resolveDefaultRoute());
  } finally {
    loading.value = false;
  }
};
</script>
