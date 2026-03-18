<template>
  <section class="login">
    <h2>欢迎回来</h2>
    <p>请输入组织 ID 与账号密码登录。</p>
    <form @submit.prevent="submit">
      <label>
        组织 ID
        <input v-model="orgId" type="text" placeholder="org-uuid" />
      </label>
      <label>
        账号
        <input v-model="username" type="text" placeholder="admin" />
      </label>
      <label>
        密码
        <input v-model="password" type="password" placeholder="••••••" />
      </label>
      <button type="submit" :disabled="loading">
        {{ loading ? "登录中..." : "登录" }}
      </button>
    </form>
    <div class="footer">
      还没有账号？
      <RouterLink to="/register">创建组织</RouterLink>
    </div>
  </section>
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
    console.log("开始登录...");
    await auth.login({
      org_id: orgId.value,
      username: username.value,
      password: password.value,
    });
    console.log("登录成功，准备跳转，当前 auth.isAuthed:", auth.isAuthed);
    await router.push("/");
    console.log("路由跳转已执行");
  } catch (error) {
    console.error("登录失败:", error);
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
