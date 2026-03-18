<template>
  <section class="login">
    <h2>创建组织</h2>
    <p>注册后会自动创建组织与管理员账号。</p>
    <form @submit.prevent="submit">
      <label>
        组织名称
        <input v-model="orgName" type="text" placeholder="PIAP Labs" />
      </label>
      <label>
        组织标识
        <input v-model="orgSlug" type="text" placeholder="piap-labs" />
      </label>
      <label>
        管理员账号
        <input v-model="username" type="text" placeholder="admin" />
      </label>
      <label>
        管理员邮箱
        <input v-model="email" type="email" placeholder="admin@piap.ai" />
      </label>
      <label>
        管理员密码
        <input v-model="password" type="password" placeholder="••••••" />
      </label>
      <button type="submit" :disabled="loading">
        {{ loading ? "创建中..." : "创建并登录" }}
      </button>
    </form>
    <div class="footer">
      已有账号？
      <RouterLink to="/login">返回登录</RouterLink>
    </div>
  </section>
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
    router.push("/");
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.login {
  width: min(420px, 100%);
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #fff;
  padding: 32px;
  border-radius: 16px;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.12);
}

form {
  display: grid;
  gap: 16px;
}

label {
  display: grid;
  gap: 6px;
  font-size: 14px;
  color: #475569;
}

input {
  height: 44px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  padding: 0 12px;
}

button {
  height: 44px;
  border: none;
  border-radius: 10px;
  background: #1b3a5c;
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}

button:disabled {
  opacity: 0.7;
  cursor: default;
}

.footer {
  font-size: 13px;
  color: #64748b;
}
</style>
