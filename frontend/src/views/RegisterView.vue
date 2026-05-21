<template>
  <div class="w-full max-w-[380px]">
    <div class="mb-8">
      <h2 class="text-2xl font-bold text-zinc-900">注册账号</h2>
      <p class="mt-2 text-sm text-zinc-500">{{ createOrg ? "创建新组织并注册首个账号" : "加入已有组织" }}</p>
    </div>

    <!-- Tab 切换 -->
    <div class="flex mb-6 bg-zinc-100 rounded-lg p-1">
      <button
        :class="createOrg ? 'bg-white shadow-sm text-zinc-900' : 'text-zinc-500'"
        class="flex-1 py-2 text-[13px] font-medium rounded-md transition-colors"
        @click="createOrg = true"
      >创建新组织</button>
      <button
        :class="!createOrg ? 'bg-white shadow-sm text-zinc-900' : 'text-zinc-500'"
        class="flex-1 py-2 text-[13px] font-medium rounded-md transition-colors"
        @click="createOrg = false"
      >加入已有组织</button>
    </div>

    <form class="flex flex-col gap-5" @submit.prevent="submit">
      <!-- 创建组织时才需要组织名称 -->
      <div v-if="createOrg" class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">组织名称</label>
        <el-input
          v-model="orgName"
          placeholder="PIAP Labs"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">
          {{ createOrg ? "组织标识" : "组织 ID / slug" }}
        </label>
        <el-input
          v-model="orgSlug"
          :placeholder="createOrg ? 'piap-labs' : 'cqupt'"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">账号</label>
        <el-input
          v-model="username"
          placeholder="zhangsan"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">邮箱</label>
        <el-input
          v-model="email"
          type="email"
          placeholder="zhangsan@piap.ai"
          size="large"
          clearable
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">密码</label>
        <el-input
          v-model="password"
          type="password"
          placeholder="••••••"
          size="large"
          show-password
          @keydown.enter="submit"
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-[13px] font-medium text-zinc-600">身份</label>
        <el-select v-model="role" size="large" class="!w-full">
          <el-option
            v-for="item in roleOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </div>

      <el-button
        type="primary"
        size="large"
        native-type="submit"
        :loading="loading"
        class="!w-full !mt-2"
        @click="submit"
      >
        {{ loading ? "注册中..." : (createOrg ? "创建并登录" : "注册并登录") }}
      </el-button>
    </form>

    <p class="mt-6 text-center text-[13px] text-zinc-400">
      已有账号？
      <RouterLink to="/login" class="text-zinc-900 font-medium hover:underline">返回登录</RouterLink>
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";
import { ElMessage } from "element-plus";

const router = useRouter();
const auth = useAuthStore();

const roleOptions = [
  { label: "管理员", value: "admin" },
  { label: "普通用户", value: "user" },
  { label: "质检专家", value: "expert" },
  { label: "应用开发者", value: "app_developer" },
  { label: "平台运营", value: "platform_operator" },
  { label: "算法工程师", value: "algorithm_engineer" },
];

const createOrg = ref(true);
const orgName = ref("");
const orgSlug = ref("");
const username = ref("");
const email = ref("");
const password = ref("");
const role = ref("admin");
const loading = ref(false);

watch(createOrg, (val) => {
  role.value = val ? "admin" : "user";
});

const submit = async () => {
  if (!orgSlug.value || !username.value || !email.value || !password.value) {
    ElMessage.warning("请填写所有必填项");
    return;
  }
  if (createOrg.value && !orgName.value) {
    ElMessage.warning("请填写组织名称");
    return;
  }
  loading.value = true;
  try {
    await auth.register({
      create_org: createOrg.value,
      org_name: createOrg.value ? orgName.value : "",
      org_slug: orgSlug.value,
      username: username.value,
      email: email.value,
      password: password.value,
      role: role.value,
    });
    router.push(auth.resolveDefaultRoute());
  } catch (e: any) {
    const msg = e?.response?.data?.message || "注册失败";
    ElMessage.error(msg);
  } finally {
    loading.value = false;
  }
};
</script>
